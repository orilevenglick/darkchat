# DarkChat
An interactive chatting website, that doesn't require any client-side javascript. Instead, it uses chunked-HTTP to stream messages in real time.

Inspired by similar websites on Tor ("the darknet"), hence the name. Over there, independence of client-side code is a requirement, as many people disable it for security reasons.

Threw it together in an afternoon, so it might not be perfectly reliable.

## Technical Details
- HTTP-server library: Sanic
- Streaming protocol: chunked HTTP
- Authentication method: JWT tokens
- Code style: spaghetti