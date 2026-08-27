export interface Env {
  API_ORIGIN: string;
}

const allowedMethods = "GET,POST,DELETE,OPTIONS";
const maxBodyBytes = 256 * 1024;

function headers(requestId: string): Headers {
  return new Headers({
    "Access-Control-Allow-Origin": "https://replace-with-web-origin.example",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Request-ID",
    "Access-Control-Allow-Methods": allowedMethods,
    "X-Request-ID": requestId,
    "Cache-Control": "no-store",
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = request.headers.get("X-Request-ID") || crypto.randomUUID();
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: headers(requestId) });
    if (!env.API_ORIGIN || env.API_ORIGIN.includes("replace-with")) return Response.json({ detail: "API origin is not configured" }, { status: 503, headers: headers(requestId) });
    if (request.method !== "GET" && Number(request.headers.get("content-length") || 0) > maxBodyBytes) return Response.json({ detail: "Request body too large" }, { status: 413, headers: headers(requestId) });

    const incoming = new URL(request.url);
    const origin = new URL(env.API_ORIGIN);
    origin.pathname = incoming.pathname;
    origin.search = incoming.search;
    const forward = new Request(origin, request);
    const response = await fetch(forward);
    const responseHeaders = headers(requestId);
    response.headers.forEach((value, key) => { if (key.toLowerCase() !== "set-cookie") responseHeaders.set(key, value); });
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  },
};
