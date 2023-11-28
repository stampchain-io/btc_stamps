import { HandlerContext, Handlers, Request, PageProps } from "$fresh/server.ts";
import { useSignal } from "@preact/signals";

import {
  get_last_x_blocks_with_client,
  connectDb,
} from "$lib/database/index.ts";
import Block from "$islands/Block.tsx";

export const handler: Handlers<BlockRow[]> = {
  async GET(_req: Request, ctx: HandlerContext) {
    const client = await connectDb();
    const blocks = await get_last_x_blocks_with_client(client, 4);
    client.close();
    return await ctx.render({
      blocks,
    })
  },
};


export default function Home(props: PageProps<BlockRow[]>) {
  const { blocks } = props.data;
  const selected = useSignal<BlockRow>(blocks[0]);
  return (
    <div class="px-4 py-8 mx-auto bg-[#000000]">
      <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>
      <div class="grid grid-cols-1 gap-4 mt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {blocks.map((block) => (
          <Block block={block} selected={selected}/>
        ))}
      </div>



    </div>
  );
}
