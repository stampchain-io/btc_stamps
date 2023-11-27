import { HandlerContext } from "$fresh/server.ts";
import { handleQuery } from "$lib/db.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { id } = ctx.params;
  try {
    if (Number.isInteger(Number(id))) {
      const data = await handleQuery(
        `SELECT * FROM StampTableV4 WHERE stamp = ?`,
        [id]
      );
      let body = JSON.stringify(
        data.rows
      );
      return new Response(body);
    } else {
      const data = await handleQuery(
        `
        SELECT * FROM StampTableV4
        WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?)
        `,
        [id, id, id]
      );
      let body = JSON.stringify(
        data.rows
      );
      return new Response(body);
    }
  } catch {
    let body = JSON.stringify({ error: `Error: Internal server error` });
    return new Response(body);
  }
};
