import { Partial } from "$fresh/runtime.ts";

import { api_get_cursed } from "$lib/controller/cursed.ts";

import { PageControl } from "$components/PageControl.tsx";
import { StampCard } from "$components/StampCard.tsx";

type CursedPageProps = {
  params: {
    stamps: StampRow[];
    total: number;
    page: number;
    pages: number;
    page_size: number;
  };
};

export const handler: Handlers<StampRow> = {
  async GET(req: Request, ctx: HandlerContext) {
    const url = new URL(req.url);
    const page = parseInt(url.searchParams.get('page') || '1');
    const page_size = parseInt(url.searchParams.get('limit') || '1000');
    const order = url.searchParams.get('order')?.toUpperCase() || 'DESC';
    const { stamps, total, pages, page: pag, page_size: limit } = await api_get_cursed(page, page_size, order);
    const data = {
      stamps,
      total,
      page: pag,
      pages,
      page_size: limit,
    }
    return await ctx.render(data);
  },
};

export default function StampPage(props: CursedPageProps) {
  const { stamps, total, page, pages, page_size } = props.data;
  return (
    <div class="w-full flex flex-col items-center">
      <PageControl page={page} pages={pages} page_size={page_size} />
      <Partial name="stamps">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 py-6 transition-opacity duration-700 ease-in-out">
          {stamps.map((stamp: StampRow) => (
            <StampCard stamp={stamp} />
          ))}
        </div>
      </Partial>
      <PageControl page={page} pages={pages} page_size={page_size} />
    </div>
  );

}