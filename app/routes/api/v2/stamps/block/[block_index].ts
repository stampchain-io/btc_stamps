import { HandlerContext } from "$fresh/server.ts";
import {
  connectDb,
  get_block_info_with_client,
  get_last_block_with_client,
  get_stamps_by_block_index_with_client,
 } from "$lib/database/index.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { block_index } = ctx.params;
  try {
    const client = await connectDb();
    const block_info = await get_block_info_with_client(client, block_index);
    const data = await get_stamps_by_block_index_with_client(client, block_index);
    const last_block = await get_last_block_with_client(client);
    let body = JSON.stringify({
      block_info: block_info.rows[0],
      data: data.rows,
      last_block: last_block.rows[0]["last_block"],
    });
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Block: ${block_index} not found` });
    return new Response(body);
  }
};
