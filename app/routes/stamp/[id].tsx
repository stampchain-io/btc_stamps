import { api_get_stamp } from "$lib/controller/stamp.ts";
import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

import { StampInfo } from "$components/StampInfo.tsx";


type StampPageProps = {
  params: {
    stamp: StampRow;
    total: number;
  };
};

export const handler: Handlers<StampRow> = {
  async GET(req: Request, ctx: HandlerContext) {
    const { id } = ctx.params;
    const { stamp, total, holders } = await api_get_stamp(id);
    const data = {
      stamp,
      holders,
      total,
    }
    return await ctx.render(data);
  },
};

export default function StampPage(props: StampPageProps) {
  const { stamp, total } = props.data;
  return (
    <div class="grid grid-col-1 sm:grid-cols-2 gap-2">
      <div>
        <img
          class="w-full h-full max-w-none object-cover image-rendering-pixelated rounded-lg"
          alt={`Stamp No. ${stamp.stamp}`}
          src={"/not-available.png"}
          //src={`/content/${stamp.tx_hash}.${get_suffix_from_mimetype(stamp.stamp_mimetype)}`}
          onError={(e) => {
            e.currentTarget.src = `/content/not-available.png`;
          }}
        />
      </div>
      {/* HISTORY */}
      <div class="text-gray-200">
        <StampInfo stamp={stamp} />
      </div>
        <StampInfo stamp={stamp} />
      <div>

      </div>
      {/* DISPENSERS */}
      <div>

      </div>
    </div>
  );

}