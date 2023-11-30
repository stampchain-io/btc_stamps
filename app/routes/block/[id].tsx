import { Handler, HandlerContext, Handlers, PageProps } from "$fresh/server.ts";
import { api_get_block_with_issuances } from "$lib/controller/block.ts";
import BlockInfo from "$islands/BlockInfo.tsx";

type BlockPageProps = {
  params: {
    id: string;
    block: BlockInfo;
  };
};

export const handler: Handlers<BlockRow[]> = {
  async GET(_req: Request, ctx: HandlerContext) {
    const block = await api_get_block_with_issuances(Number(ctx.params.id));
    return await ctx.render({
      block: block,
    });
  },
};

export default function BlockPage(props: PageProps) {
  const { block } = props.data;
  const { block_info, data: issuances } = block;
  return (
    <div class="px-4 py-8 mx-auto bg-[#000000]">
      <h1 class="text-2xl text-center text-[#ffffff]">Bitcoin Stamps</h1>

      <BlockInfo block={block} />
    </div>
  );
}
