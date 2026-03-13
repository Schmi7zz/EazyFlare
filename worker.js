/*
 * EazyFlare — CORS Proxy Worker v3
 * 
 * Browser sends: X-CF-Token / X-CF-Email / X-CF-Key
 * Worker maps:   Authorization / X-Auth-Email / X-Auth-Key
 * 
 * This avoids Cloudflare stripping X-Auth-* headers on internal requests.
 * Paste in Workers editor → Deploy
 */

var CF_API = "https://api.cloudflare.com/client/v4";

addEventListener("fetch", function(event) {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  var origin = request.headers.get("Origin") || "*";

  var cors = {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-CF-Token, X-CF-Email, X-CF-Key",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400"
  };

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  var url = new URL(request.url);

  // Root path = health check
  if (url.pathname === "/" || url.pathname === "") {
    var respH = new Headers(cors);
    respH.set("Content-Type", "application/json");
    return new Response(
      JSON.stringify({ success: true, message: "EazyFlare Proxy is running" }),
      { status: 200, headers: respH }
    );
  }

  var targetUrl = CF_API + url.pathname + url.search;

  // Build headers for Cloudflare API
  var apiHeaders = new Headers();
  apiHeaders.set("Content-Type", "application/json");

  // Map custom headers to CF API headers
  var token = request.headers.get("X-CF-Token");
  var email = request.headers.get("X-CF-Email");
  var key = request.headers.get("X-CF-Key");

  if (token) {
    apiHeaders.set("Authorization", "Bearer " + token);
  }
  if (email) {
    apiHeaders.set("X-Auth-Email", email);
  }
  if (key) {
    apiHeaders.set("X-Auth-Key", key);
  }

  var init = {
    method: request.method,
    headers: apiHeaders
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      var body = await request.text();
      if (body && body.length > 0) {
        init.body = body;
      }
    } catch(e) {}
  }

  try {
    var resp = await fetch(targetUrl, init);
    var data = await resp.text();

    var rh = new Headers(cors);
    rh.set("Content-Type", "application/json");

    return new Response(data, { status: resp.status, headers: rh });
  } catch(err) {
    var eh = new Headers(cors);
    eh.set("Content-Type", "application/json");
    return new Response(
      JSON.stringify({ success: false, errors: [{ message: err.message }] }),
      { status: 502, headers: eh }
    );
  }
}