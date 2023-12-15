import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

export function StampCard({ stamp, kind = 'stamp' }: { stamp: StampRow, kind: "cursed" | "stamp" | "named" }) {
  return (
    <a href={`/stamp/${stamp.tx_hash}`}
      class="border rounded-lg text-center text-sm uppercase"
      >
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
        <p class="text-gray-200 border-b">
          {stamp.cpid}
        </p>
        <p class="text-gray-200">
          Creator: {
            stamp.creator_name ?
              stamp.creator_name :
              short_address(stamp.creator, 6)
          }
        </p>
      </div>
    </a>
  )
}