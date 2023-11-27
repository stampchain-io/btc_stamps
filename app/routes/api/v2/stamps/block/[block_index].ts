import { HandlerContext } from "$fresh/server.ts";
import {query} from "$lib/db.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { block_index } = ctx.params;
  try {
    const data = await query(
      `
      SELECT * FROM StampTableV4
      WHERE block_index = ?
      AND is_btc_stamp IS NOT NULL
      ORDER BY stamp
      `,
      [block_index],
    );
    let body = JSON.stringify(
      data.rows
    );
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Block: ${block_index} not found` });
    return new Response(body);
  }
};
