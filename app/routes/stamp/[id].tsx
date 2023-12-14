import { api_get_stamp } from "$lib/controller/stamp.ts";
import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

import { StampInfo } from "$components/StampInfo.tsx";
import { StampHistory } from "$components/StampHistory.tsx";
import { Stamp } from "$components/Stamp.tsx";


type StampPageProps = {
  params: {
    stamp: StampRow;
    total: number;
  };
};

export const handler: Handlers<StampRow> = {
  async GET(req: Request, ctx: HandlerContext) {
    const { id } = ctx.params;
    const res = await api_get_stamp(id);
    if (!res) {
      return ctx.renderNotFound();
    }
    const { stamp, holders, total, sends } = res;
    const data = {
      stamp,
      holders,
      sends,
      total,
    }
    return await ctx.render(data);
  },
};
export default function StampPage(props: StampPageProps) {
  const { stamp, sends, holders, total } = props.data;

  return (
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4">
      {/* Stamp Component */}
      <div class="flex flex-col items-center justify-center order-1 sm:order-1">
        <Stamp stamp={stamp} className="w-full" />
      </div>

      {/* Stamp History Component */}
      <div class="order-3 sm:order-2 text-gray-200">
        <StampHistory holders={holders} sends={sends} className="w-full" />
      </div>

      {/* Stamp Info Component */}
      <div class="order-2 sm:order-3">
        <StampInfo stamp={stamp} className="w-full" />
      </div>

      {/* Otros componentes aquí */}
      {/* ... */}
    </div>
  );
}
