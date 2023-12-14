import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { short_address } from "utils/util.ts";

dayjs.extend(relativeTime);

export function StampSends({ sends }: { sends: SendRow[] }) {
  return (
    <div class="relative overflow-x-auto shadow-md sm:rounded-lg max-h-96 max-w-96">
      <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
        <caption class="p-5 text-lg font-semibold text-left rtl:text-right text-gray-900 bg-white dark:text-white dark:bg-gray-800">
          Activity
        </caption>
        <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
          <tr>
            <th scope="col" class="px-6 py-3">From</th>
            <th scope="col" class="px-6 py-3">To</th>
            <th scope="col" class="px-6 py-3">Qty</th>
            <th scope="col" class="px-6 py-3">Unitary price</th>
            <th scope="col" class="px-6 py-3">Memo</th>
            <th scope="col" class="px-6 py-3">Tx_hash</th>
            <th scope="col" class="px-6 py-3">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {sends.map((send: SendRow) => {
            const kind = send.is_btc_stamp ? "stamp" : send.cpid.startsWith("A") ? "cursed" : "named"

            return (
              <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700">
                <td class="px-6 py-4">
                  {send.from ? short_address(send.from) : "NULL"}
                </td>
                <td class="px-6 py-4">
                  {send.to ? short_address(send.to) : "NULL"}
                </td>
                <td class="px-6 py-4 text-sm">{send.quantity}</td>
                <td class="px-6 py-4 text-sm">
                  {
                    send.satoshirate ?
                      `${send.satoshirate / 100000000} BTC` :
                      '0 BTC'
                  }
                </td>
                <td class="px-6 py-4 text-sm">{send.memo || 'transfer'}</td>
                <td class="px-6 py-4 text-sm">{short_address(send.tx_hash)}</td>
                <td class="px-6 py-4 text-sm">{dayjs(Number(send.block_time) * 1000).fromNow()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>

  )
}