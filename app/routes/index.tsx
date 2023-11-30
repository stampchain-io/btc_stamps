import { HandlerContext, Handlers, PageProps } from "$fresh/server.ts";
import { useSignal } from "@preact/signals";

import {
  connectDb,
  get_last_x_blocks_with_client,
} from "$lib/database/index.ts";
import Block from "$islands/BlockSelector.tsx";
import BlockInfo from "$islands/BlockInfo.tsx";

export const handler: Handlers<BlockRow[]> = {
  async GET(_req: Request, ctx: HandlerContext) {
    const client = await connectDb();
    const blocks = await get_last_x_blocks_with_client(client, 4);
    client.close();
    return await ctx.render({
      blocks,
    });
  },
};

type IndexProps = {
  data: {
    blocks: BlockRow[];
  };
};

export default function Home(props: IndexProps) {
  const { blocks } = props.data;
  const selected = useSignal<BlockRow>(blocks[0]);
  return (
    <div class="px-4 py-8 mx-auto bg-[#000000]">
      <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>
      <div class="grid grid-cols-1 gap-4 mt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {blocks.map((block: BlockRow) => (
          <Block block={block} selected={selected} />
        ))}
      </div>
    </div>
  );
}
