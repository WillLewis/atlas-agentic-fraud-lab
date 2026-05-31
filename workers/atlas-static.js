const BASE_PATH = "/atlas";

function jsonResponse(body, init) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...(init?.headers ?? {}),
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === BASE_PATH) {
      url.pathname = `${BASE_PATH}/`;
      return Response.redirect(url.toString(), 308);
    }

    if (!url.pathname.startsWith(`${BASE_PATH}/`)) {
      return new Response("Not found", { status: 404 });
    }

    if (
      url.pathname === `${BASE_PATH}/api` ||
      url.pathname.startsWith(`${BASE_PATH}/api/`)
    ) {
      return jsonResponse(
        {
          error: "Project Atlas public deployment is static. The local mock API is not exposed.",
        },
        { status: 404 },
      );
    }

    const assetUrl = new URL(request.url);
    assetUrl.pathname = url.pathname.slice(BASE_PATH.length) || "/";
    return env.ASSETS.fetch(new Request(assetUrl, request));
  },
};
