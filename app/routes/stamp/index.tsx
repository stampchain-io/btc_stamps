import { Partial } from "$fresh/runtime.ts";

import { api_get_stamps } from "$lib/controller/stamp.ts";
import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

import { PageControl } from "$components/PageControl.tsx";

type StampPageProps = {
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
    const { stamps, total, pages, page: pag, page_size: limit } = await api_get_stamps(page, page_size, order);
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

export default function StampPage(props: StampPageProps) {
  const { stamps, total, page, pages, page_size } = props.data;
  return (
    <div class="w-full flex flex-col items-center">
      <PageControl page={page} pages={pages} page_size={page_size} />
      <Partial name="stamps">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 py-6">
          {stamps.map((stamp: StampRow) => (
            <a href={`/stamp/${stamp.tx_hash}`}
              class="border rounded-lg text-center text-sm">
              <div class="relative pb-[100%] w-full overflow-hidden">
                <img
                  class="absolute top-0 left-0 w-full h-full max-w-none object-cover image-rendering-pixelated rounded-t-lg"
                  alt={`Stamp No. ${stamp.stamp}`}
                  src={`/content/${stamp.tx_hash}.${get_suffix_from_mimetype(stamp.stamp_mimetype)}`}
                  onError={(e) => {
                    e.currentTarget.src = `/content/not-available.png`;
                  }}
                />
              </div>
              <div>
                <div class="flex justify-around truncate border-b border-t">
                  <p class="text-gray-200">
                    Stamp: #{stamp.stamp}
                  </p>
                  <p class="text-gray-200">
                    Qty: {
                      stamp.divisible ?
                        (stamp.supply / 100000000).toFixed(2) :
                        stamp.supply > 100000 ?
                          "+100000" :
                          stamp.supply
                    }
                  </p>
                </div>
                <p class="text-gray-200">
                  Creator: {
                    stamp.creator_name ?
                      stamp.creator_name :
                      short_address(stamp.creator, 6)
                  }
                </p>
              </div>
            </a>
          ))}
        </div>
      </Partial>
      <PageControl page={page} pages={pages} page_size={page_size} />
    </div>
  );

}