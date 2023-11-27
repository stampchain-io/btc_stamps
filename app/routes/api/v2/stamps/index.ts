import { HandlerContext } from "$fresh/server.ts";
import { query } from "$lib/db.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  try {

    const data = await query(
      `
        SELECT * FROM StampTableV4
        WHERE is_btc_stamp IS NOT NULL
        ORDER BY stamp
        `,
      []
    );
    let body = JSON.stringify(
      data.rows
    );
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Error: Internal server error` });
    return new Response(body);
  }
};
