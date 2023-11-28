import { HandlerContext } from "$fresh/server.ts";
import {
  connectDb,
  get_last_block_with_client,
  get_issuances_by_stamp_with_client,
  get_issuances_by_identifier_with_client,
} from "$lib/database/index.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { id } = ctx.params;
  try {
    const client = await connectDb();
    let data;
    if (Number.isInteger(Number(id))) {
      data = await get_issuances_by_stamp_with_client(client, id)
    } else {
      data = await get_issuances_by_identifier_with_client(client, id);
    }
    const last_block = await get_last_block_with_client(client);
    client.close();
    let body = JSON.stringify({
      data: data.rows,
      last_block: last_block.rows[0]["last_block"],
    });
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Error: Internal server error` });
    return new Response(body);
  }
};
