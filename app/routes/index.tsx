export function handler(req: Request): Response {
  return new Response("", {
    status: 307,
    headers: { Location: "/block/last" },
  });
}
