import { Handler, HandlerContext, Handlers, PageProps } from "$fresh/server.ts";
import {
  api_get_block_with_issuances,
  api_get_last_block,
  api_get_related_blocks,
} from "$lib/controller/block.ts";
import BlockInfo from "$components/BlockInfo.tsx";
import Block from "$islands/BlockSelector.tsx";
import { useSignal } from "@preact/signals";

type BlockPageProps = {
  params: {
    id: string;
    block: BlockInfo;
  };
};

export const handler: Handlers<BlockRow[]> = {
  async GET(_req: Request, ctx: HandlerContext) {
    if (!ctx.params.id || isNaN(Number(ctx.params.id))) {
      const { last_block } = await api_get_last_block();
      return new Response("", {
        status: 307,
        headers: { Location: `/block/${last_block}` },
      });
    } else {
      const block = await api_get_block_with_issuances(Number(ctx.params.id));
      const related_blocks = await api_get_related_blocks(
        Number(ctx.params.id),
      );
      return await ctx.render({
        block,
        related_blocks,
      });
    }
  },
};

export default function BlockPage(props: PageProps) {
  const { block, related_blocks } = props.data;
  const { block_info, data: issuances } = block;
  const { blocks, last_block } = related_blocks;
  console.log(related_blocks);
  const selected = useSignal<BlockRow>(
    blocks.find((b: BlockRow) => b.block_index === block_info.block_index),
  );
  return (
    <div class="sm:px-4 py-8 mx-auto bg-[#000000]">
      <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>
      <div class="grid grid-cols-1 gap-4 mt-8 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 py-2 ">
        {blocks.map((block: BlockRow) => (
          <Block block={block} selected={selected} />
        ))}
      </div>
      <BlockInfo block={block} />
    </div>
  );
}
