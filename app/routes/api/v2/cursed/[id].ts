import { HandlerContext } from "$fresh/server.ts";
import {
  connectDb,
  get_stamp_by_stamp_with_client,
  get_stamp_by_identifier_with_client,
} from "$lib/db.ts";

export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { id } = ctx.params;
  try {
    const client = await connectDb();
    if (Number.isInteger(Number(id))) {
      const data = await get_stamp_by_stamp_with_client(client, id)
      let body = JSON.stringify(
        data.rows
      );
      return new Response(body);
    } else {
      const data = await get_stamp_by_identifier_with_client(client, id);
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
