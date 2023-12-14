import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import {short_address} from "utils/util.ts";
import { StampKind } from "$/components/StampKind.tsx";

dayjs.extend(relativeTime);

export function StampInfo({ stamp }: { stamp: StampRow }) {
  const timestamp = new Date(stamp.timestamp)
  const kind = stamp.is_btc_stamp ? "stamp" : stamp.cpid.startsWith("A") ? "cursed" : "named"
  return (
    <div class="flex flex-col uppercase text-gray-200">
      <div class="flex justify-around items-center truncate border-b border-t">
        <p>
          Stamp: #{stamp.stamp}
        </p>
        <StampKind kind={kind} />
        <p>
          Supply: {
            stamp.divisible ?
              (stamp.supply / 100000000).toFixed(2) :
              stamp.supply > 100000 ?
                "+100000" :
                stamp.supply
          }
        </p>
      </div>
      <div class="flex justify-around truncate border-b border-t">
        <p>
          CPID: {stamp.cpid}
        </p>
      </div>
      <div class="flex justify-around truncate border-b border-t">
        <p>
          Creator: {
            stamp.creator_name ?
              stamp.creator_name :
              short_address(stamp.creator, 6)
          }
        </p>
      </div>
      <div class="flex justify-around truncate border-b border-t">
        <p>
          Created: {timestamp.toLocaleDateString()} ({dayjs(timestamp).fromNow()})
        </p>
      </div>

    </div>
  );
}