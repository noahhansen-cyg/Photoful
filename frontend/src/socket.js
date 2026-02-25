import { io } from "socket.io-client";

// Single shared socket instance for the whole app.
// Connects to the same host that served the page (proxied to Flask in dev).
const socket = io({ autoConnect: false });

export default socket;
