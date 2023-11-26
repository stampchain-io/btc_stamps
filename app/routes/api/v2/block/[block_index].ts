import { HandlerContext } from "$fresh/server.ts";
import {load} from "$std/dotenv/mod.ts";
import {query} from "../../../../lib/db.ts";

await load();
export const handler = async (_req: Request, ctx: HandlerContext): Response => {
  const { block_index } = ctx.params;
  try {
    const data = await query(
      "SELECT * FROM blocks WHERE block_index = ??",
      [block_index],
    );
    console.log({data});
    let body = JSON.stringify(data);
    return new Response(body);
  } catch {
    let body = JSON.stringify({ error: `Block: ${block_index} not found` });
    return new Response(body);
  }

};
