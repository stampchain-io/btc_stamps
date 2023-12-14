import { HandlerContext } from "$fresh/server.ts";
import {
  connectDb,
  get_cursed_by_ident_with_client,
  get_last_block_with_client,
  get_total_cursed_by_ident_with_client,
} from "$lib/database/index.ts";
import { PROTOCOL_IDENTIFIERS } from "$lib/utils/protocol.ts";

export const handler = async (req: Request, ctx: HandlerContext): Response => {
  const { ident } = ctx.params;
  if (!PROTOCOL_IDENTIFIERS.includes(ident.toUpperCase())) {
    let body = JSON.stringify({ error: `Error: ident: ${ident} not found` });
    return new Response(body);
  }
  try {
    const url = new URL(req.url);
    const limit = Number(url.searchParams.get("limit")) || 1000;
    const page = Number(url.searchParams.get("page")) || 0;
    const client = await connectDb();
    const data = await get_cursed_by_ident_with_client(client, ident.toUpperCase(), limit, page);
    const total = await get_total_cursed_by_ident_with_client(client, ident.toUpperCase());
    const last_block = await get_last_block_with_client(client);
    let body = JSON.stringify({
      ident: ident.toUpperCase(),
      data: data.rows,
      limit,
      page,
      total: total.rows[0]['total'],
      last_block: last_block.rows[0]['last_block'],
    });
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Error: stamps with ident: ${ident} not found` });
    return new Response(body);
  }
};
