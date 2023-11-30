import { HandlerContext } from "$fresh/server.ts";

export function handler(req: Request, ctx: HandlerContext): Response {
  return new Response("", {
    status: 307,
    headers: { Location: `/stamps/${ctx.params.imgpath}` },
  });
}
