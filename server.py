import asyncio
from asyncio.exceptions import CancelledError
import secrets
import time
import html
from typing import List, Dict, Tuple, Union

import sanic, sanic.request, sanic.response
import jwt


MESSAGE_INPUT_NAME = "msg"
NICK_INPUT_NAME = "nick"
COOKIE_NAME = "jwt"
CONTENT_TYPE = "text/html; charset=utf-8"
CHAT_HTML_BEGIN = f"""<!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DarkChat</title>
    <style>
      body {{ margin: 0; padding: 0; }}
      .container {{
        width: 80vw; max-height: 90vh; margin: auto; padding-top: 2%; padding-bottom: 2%;
        display: flex; flex-direction: column;
      }}
      .message-form {{ display: flex; }}
      .message-input {{ flex-grow: 1; }}
      .submit {{ margin: 1em; }}
      ul.messages {{
        list-style: none;
        display: flex;
        flex-direction: column-reverse;
        padding: 0;
        overflow-y: scroll;
      }}
      li.message {{ width: 100% }}
      li.message:nth-child(even) {{ background-color: lightgray; }}
      li.message:nth-child(odd) {{ background-color: rgb(228, 228, 228); }}
      .sender {{ font-weight: bold; }}
    </style>
  </head>
  <body>
    <div class="container">
      <form action="/" method="POST" class="message-form">
        <input name="{MESSAGE_INPUT_NAME}" class="message-input" />
        <input type="submit" value="Send" />
      </form>
      <ul class="messages">
"""
# CHAT_HTML_END = """
#     </ul>
#   </body>
# </html>
# """
JWT_SECRET = secrets.token_hex(32)

REGISTER_HTML = f"""<!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DarkChat</title>
    <style>
      .content {{
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
      }}
      .submit {{
        margin: 1em;
      }}
    </style>
  </head>
  <body>
      <form action="/register" method="POST" class="content">
        <h1>Enter Nickname</h1>
        <input name="{NICK_INPUT_NAME}" />
        <br />
        <input class="submit" type="submit" value="Start chatting" />
      </form>
  </body>
  </html>
"""



app = sanic.Sanic("darkchat")
nicks: Dict[str, int] = {}


class MessageIterator:
    def __init__(self, messages: "Messages"):
        self.messages = messages
        self.index = -1
        self.lock = asyncio.Lock()
    
    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index + 1 >= len(self.messages):
            await self.lock.acquire()
            await self.lock.acquire()
            self.lock.release()
        
        self.index += 1
        return self.messages[self.index]

    def update(self):
        if self.lock.locked:
            self.lock.release()

    def close(self):
        self.messages.close_iterator(self)


class Messages:
    def __init__(self) -> None:
        self.queue: List[Tuple[str, str]] = []
        self.iters: List[MessageIterator] = []

    def put(self, item: str):
        self.queue.append(item)
        for msg_iter in self.iters:
            msg_iter.update()

    def __aiter__(self) -> MessageIterator:
        new_iter = MessageIterator(self)
        self.iters.append(new_iter)
        return new_iter
    
    def close_iterator(self, iterator: MessageIterator):
        self.iters.remove(iterator)
    
    def __len__(self):
        return len(self.queue)
    
    def __getitem__(self, key):
        return self.queue[key]


messages = Messages()


async def show_chat(request: sanic.request.Request) -> sanic.response.StreamingHTTPResponse:
    response = await request.respond(content_type=CONTENT_TYPE)

    await response.send(CHAT_HTML_BEGIN)

    try:
        msg_iter = messages.__aiter__()
        async for msg in msg_iter:
            sender = html.escape(msg[0])
            text = html.escape(msg[1])
            await response.send(f'<li class="message"><span class="sender">{sender}:</span> {text}</li>')
    except CancelledError:
        pass
    finally:
        msg_iter.close()
        # await response.send(HTML_END)
        # await response.eof()
        # return response

def uses_jwt(func):
    def wrapper(request: sanic.request.Request):
        redirect_response = sanic.response.redirect("/register")
        del redirect_response.cookies[COOKIE_NAME]

        cookie = request.cookies.get(COOKIE_NAME)
        if cookie is None:
            return redirect_response
        
        try:
            content = jwt.decode(cookie, JWT_SECRET, algorithms=["HS256"])
        except jwt.exceptions.InvalidSignatureError:
            return redirect_response

        if "nick" not in content or "expire" not in content or content["expire"] < time.time():
            return redirect_response
        
        return func(request, content["nick"])
    
    return wrapper


@app.get("/register")
def register(request: sanic.request.Request) -> sanic.HTTPResponse:
    return sanic.response.html(REGISTER_HTML)

@app.post("/register")
def register(request: sanic.request.Request) -> sanic.HTTPResponse:
    if NICK_INPUT_NAME not in request.form or request.form[NICK_INPUT_NAME][-1] == "":
        return sanic.response.text("error", status=400)
    
    nick = request.form[NICK_INPUT_NAME][-1]
    last_expire = nicks.get(nick)

    if last_expire is not None and last_expire > time.time():
        return sanic.response.text("nick already exists", status=409)
    
    expiration = int(time.time()) + 60*60*8  # 8 hours from now
    nicks[nick] = expiration
    token = jwt.encode({"nick": nick, "expire": expiration}, JWT_SECRET, algorithm="HS256")

    response = sanic.response.redirect("/")
    response.cookies[COOKIE_NAME] = token
    response.cookies[COOKIE_NAME]
    return response

@app.get("/")
@uses_jwt
async def chat(request: sanic.request.Request, nick: str) -> sanic.response.StreamingHTTPResponse:
    return await show_chat(request)

@app.post("/")
@uses_jwt
async def post_message(request: sanic.request.Request, nick: str) -> Union[sanic.response.StreamingHTTPResponse, sanic.HTTPResponse]:
    if MESSAGE_INPUT_NAME not in request.form:
        return sanic.response.text("error", status=400)
    
    msg = request.form[MESSAGE_INPUT_NAME][-1]
    messages.put((nick, msg))
    return await show_chat(request)
    

app.run("0.0.0.0", 1337, debug=True)