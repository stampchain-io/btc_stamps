import { HandlerContext } from "$fresh/server.ts";
import {
  connectDb,
  handleQueryWithClient,
  get_last_block_with_client,
  get_total_cursed_with_client,
 } from "$lib/db.ts";

export const handler = async (req: Request, _ctx: HandlerContext): Response => {
  try {
    const url = new URL(req.url);
    const limit = Number(url.searchParams.get("limit")) || 1000;
    const page = Number(url.searchParams.get("page")) || 0;
    const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
    const client = await connectDb();
    const data = await handleQueryWithClient(
      client,
      `
        SELECT * FROM StampTableV4
        WHERE is_btc_stamp IS NULL
        AND is_reissue IS NULL
        ORDER BY tx_index
        LIMIT ? OFFSET ?;
        `,
      [limit, offset]
    );
    const last_block = await get_last_block_with_client(client);
    const total = await get_total_cursed_with_client(client);
    client.close();
    let body = JSON.stringify({
      data: data.rows,
      limit,
      page,
      total: total.rows[0]["total"],
      last_block: last_block.rows[0]["last_block"],
    });
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Error: Internal server error` });
    return new Response(body);
  }
};
