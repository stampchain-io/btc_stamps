import { HandlerContext } from "$fresh/server.ts";
import { api_get_block } from "$lib/controller/block.ts";

export const handler = async (_req: Request, ctx: HandlerContext) => {
  const { block_index } = ctx.params;
  try {
    const response = await api_get_block(parseInt(block_index));
    const body = JSON.stringify(response);
    return new Response(body);
  } catch {
    const body = JSON.stringify({ error: `Block: ${block_index} not found` });
    return new Response(body);
  }
};
