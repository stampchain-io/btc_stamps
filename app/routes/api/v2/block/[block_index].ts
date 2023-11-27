import { HandlerContext } from "$fresh/server.ts";
import { handleQuery } from "$lib/db.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { block_index } = ctx.params;
  try {
    const block_info = await handleQuery(
      `
      SELECT * FROM blocks
      WHERE block_index = ?
      `,
      [block_index],
    );
    const stamps = await handleQuery(
      `
      SELECT * FROM StampTableV4
      WHERE block_index = ?
      AND (is_btc_stamp IS NOT NULL
      OR is_reissue IS NOT NULL)
      ORDER BY stamp
      `,
      [block_index],
    );
    let body = JSON.stringify(
      {
        block_info: block_info.rows[0],
        issuances: stamps.rows
      }
    );
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Block: ${block_index} not found` });
    return new Response(body);
  }
};
