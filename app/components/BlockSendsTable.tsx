import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

dayjs.extend(relativeTime);

interface BlockSendsTableProps {
  block:{
    block_info: BlockInfo;
    issuances: StampRow[];
    sends: SendRow[];
  }
}

export default function BlockSendsTable(props: BlockSendsTableProps) {
  const { block_info, sends } = props.block;

  return (
    <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
      <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
        <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
          <tr>
            <th scope="col" class="px-6 py-3">From</th>
            <th scope="col" class="px-6 py-3">To</th>
            <th scope="col" class="px-6 py-3">Cpid</th>
            <th scope="col" class="px-6 py-3">Tick</th>
            <th scope="col" class="px-6 py-3">Qty</th>
            <th scope="col" class="px-6 py-3">Memo</th>
            <th scope="col" class="px-6 py-3">Tx_hash</th>
            <th scope="col" class="px-6 py-3">Tx_index</th>
            <th scope="col" class="px-6 py-3">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {sends.map((send: SendRow) => {
            return (
              <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700">
                <td class="px-6 py-4">
                  {send.from ? short_address(send.from): "NULL"}
                </td>
                <td class="px-6 py-4">
                  {send.to ? short_address(send.to) : "NULL"}
                </td>
                <td class="px-6 py-4 text-sm">{send.cpid}</td>
                <td class="px-6 py-4 text-sm">
                  {send.tick ? send.tick : "NULL"}
                </td>
                <td class="px-6 py-4 text-sm">{send.quantity}</td>
                <td class="px-6 py-4 text-sm">{send.memo}</td>
                <td class="px-6 py-4 text-sm">{short_address(send.tx_hash)}</td>
                <td class="px-6 py-4 text-sm">{send.tx_index}</td>
                <td class="px-6 py-4 text-sm">{dayjs(Number(block_info.block_time) * 1000).fromNow()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  )
}