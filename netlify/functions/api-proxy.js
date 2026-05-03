const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type, authorization",
  "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
};

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers: JSON_HEADERS, body: "" };
  }

  const suffix = apiSuffix(event.path || "");
  const backendOrigin = (process.env.BIOPHARMA_API_ORIGIN || "").replace(/\/$/, "");
  if (!backendOrigin) {
    return fallbackResponse(suffix, event.httpMethod);
  }

  const targetUrl = `${backendOrigin}/api${suffix}${event.rawQuery ? `?${event.rawQuery}` : ""}`;
  const headers = requestHeaders(event.headers || {});
  const response = await fetch(targetUrl, {
    method: event.httpMethod,
    headers,
    body: ["GET", "HEAD"].includes(event.httpMethod) ? undefined : event.body,
    redirect: "manual",
  });

  return {
    statusCode: response.status,
    headers: responseHeaders(response.headers),
    body: await response.text(),
  };
};

function apiSuffix(path) {
  const marker = "/.netlify/functions/api-proxy";
  if (path.startsWith(marker)) {
    return path.slice(marker.length) || "";
  }
  if (path.startsWith("/api")) {
    return path.slice("/api".length) || "";
  }
  return "";
}

function fallbackResponse(suffix, method) {
  if (method === "GET" && suffix === "/health") {
    return jsonResponse(200, {
      status: "warning",
      service: "biopharma-agent-netlify",
      message: "Static Workbench is deployed. Configure BIOPHARMA_API_ORIGIN to connect the Python API backend.",
      features: ["static_frontend", "api_proxy"],
    });
  }
  if (method === "GET" && suffix === "/config") {
    return jsonResponse(200, {
      provider: "not-configured",
      base_url: "",
      model: "",
      has_api_key: false,
      storage_backend: "netlify-static",
      analysis_store: "",
      presets: {},
    });
  }
  return jsonResponse(503, {
    error: "backend_not_configured",
    message: "Set BIOPHARMA_API_ORIGIN in Netlify environment variables to proxy this request to a running Biopharma Agent API service.",
  });
}

function jsonResponse(statusCode, payload) {
  return {
    statusCode,
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  };
}

function requestHeaders(headers) {
  const blocked = new Set(["host", "content-length", "connection"]);
  return Object.fromEntries(
    Object.entries(headers).filter(([key]) => !blocked.has(String(key).toLowerCase())),
  );
}

function responseHeaders(headers) {
  const result = { "access-control-allow-origin": "*" };
  const contentType = headers.get("content-type");
  if (contentType) {
    result["content-type"] = contentType;
  }
  return result;
}
