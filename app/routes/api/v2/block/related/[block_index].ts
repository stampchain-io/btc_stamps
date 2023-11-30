import { HandlerContext, Handlers, Request } from "$fresh/server.ts";
import {
  connectDb,
  get_last_x_blocks_with_client,
} from "$lib/database/index.ts";
import { api_get_related_blocks } from "$lib/controller/block.ts";

export const handler: Handlers = {
  async GET(_req: Request, ctx: HandlerContext) {
    const block_index = parseInt(ctx.params.block_index);

    if (Number.isNaN(block_index)) {
      return new Response(
        JSON.stringify({
          error: "Invalid number provided. Must be a number between 1 and 100.",
        }),
        {
          status: 400, // Bad Request
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }

    try {
      const blocks = await api_get_related_blocks(block_index);
      return new Response(JSON.stringify(blocks), {
        headers: {
          "Content-Type": "application/json",
        },
      });
    } catch (error) {
      console.error("Failed to get last blocks:", error);
      return new Response(
        JSON.stringify({
          error: "Failed to retrieve blocks from the database.",
        }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }
  },
};
