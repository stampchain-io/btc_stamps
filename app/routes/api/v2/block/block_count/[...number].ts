import {
  HandlerContext,
  Handlers,
  Request,
} from "$fresh/server.ts";
import { get_last_x_blocks_with_client, connectDb } from "$lib/database/index.ts";

export const handler: Handlers = {
  async GET(_req: Request, ctx: HandlerContext) {
    let number = ctx.params.number ? parseInt(ctx.params.number) : 1;

    if (Number.isNaN(number) || number < 1 || number > 100) {
      return new Response(JSON.stringify({ error: "Invalid number provided. Must be a number between 1 and 100." }), {
        status: 400, // Bad Request
        headers: {
          "Content-Type": "application/json",
        },
      });
    }
    
    try {
      const client = await connectDb();
      const lastBlocks = await get_last_x_blocks_with_client(client, number);
      await client.close();
      return new Response(JSON.stringify(lastBlocks), {
        headers: {
          "Content-Type": "application/json",
        },
      });
    } catch (error) {
      console.error('Failed to get last blocks:', error);
      return new Response(JSON.stringify({ error: "Failed to retrieve blocks from the database." }), {
        status: 500, // Internal Server Error
        headers: {
          "Content-Type": "application/json",
        },
      });
    }
  },
};
