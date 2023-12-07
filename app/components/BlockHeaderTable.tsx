import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

interface BlockHeaderTableProps {
  block:{
    block_info: BlockInfo;
    issuances: StampRow[];
    sends: SendRow[];
  }
}

export default function BlockHeaderTable(props: BlockHeaderTableProps) {
  const { block_info, issuances, sends } = props.block;
  const time = new Date(Number(block_info.block_time) * 1000);

  return (
    <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
      <tbody>
        <tr>
          <th scope="row" class="px-6 py-3">Block Hash</th>
          <td>{short_address(block_info.block_hash)}</td>
        </tr>
        <tr >
          <th scope="row" class="px-6 py-3">Time</th>
          <td>{time.toLocaleString()}</td>
        </tr>
        <tr>
          <th scope="row" class="px-6 py-3">Height</th>
          <td>{block_info.block_index}</td>
        </tr>
        <tr>
          <th scope="row" class="px-6 py-3">Issuances</th>
          <td>{issuances.length}</td>
        </tr>
        <tr>
          <th scope="row" class="px-6 py-3">Sends</th>
          <td>{sends.length}</td>
        </tr>
      </tbody>
    </table>
  )
}