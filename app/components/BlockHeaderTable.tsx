import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { short_address } from "$lib/utils/util.ts";

dayjs.extend(relativeTime);

interface BlockHeaderTableProps {
  block: {
    block_info: BlockInfo;
    issuances: StampRow[];
    sends: SendRow[];
  }
}

export default function BlockHeaderTable(props: BlockHeaderTableProps) {
  const { block_info, issuances, sends } = props.block;

  return (
    <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
      <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
        <tbody>
          <tr class="border-b">
            <th scope="row" class="whitespace-nowrap px-6 py-3">Block Index</th>
            <td class="whitespace-nowrap">{block_info.block_index}</td>
            <th scope="row" class="whitespace-nowrap px-6 py-3">Block Hash</th>
            <td class="whitespace-nowrap">{short_address(block_info.block_hash)}</td>
            <th scope="row" class="px-6 py-3">Time</th>
            <td class="whitespace-nowrap">{dayjs(Number(block_info.block_time) * 1000).fromNow()}</td>
          </tr>
          <tr class="border-b">
            <th scope="row" class="whitespace-nowrap px-6 py-3">Ledger Hash</th>
            <td class="whitespace-nowrap">{short_address(block_info.ledger_hash)}</td>
            <th scope="row" class="whitespace-nowrap px-6 py-3">Txlist Hash</th>
            <td class="whitespace-nowrap">{short_address(block_info.txlist_hash)}</td>
            <th scope="row" class="whitespace-nowrap px-6 py-3">Txlist Hash</th>
            <td class="whitespace-nowrap">{short_address(block_info.messages_hash)}</td>
          </tr>
          <tr class="border-b">
            <th scope="row" class="px-6 py-3">Issuances</th>
            <td class="whitespace-nowrap">{issuances.length}</td>
            <th scope="row" class="px-6 py-3">Sends</th>
            <td class="whitespace-nowrap">{sends.length}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}