import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";
import Stamp from "$/components/Stamp.tsx";

dayjs.extend(relativeTime);

interface BlockInfoProps {
  block: BlockInfo;
}

export default function BlockInfo(props: BlockInfoProps) {
  const { block } = props;
  const { block_info, data: issuances } = block;
  const time = new Date(Number(block_info.block_time) * 1000);

  return (
    <div class="border p-1 relative overflow-x-auto shadow-md sm:rounded-lg">
      <table class=" w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
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
        </tbody>
      </table>
      <div class="text-2xl p-2 text-[#ffffff]">
        <h2>Issuances</h2>
      </div>
      <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
        <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
          <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              <th scope="col" class="px-6 py-3">Image</th>
              <th scope="col" class="px-6 py-3">Stamp</th>
              <th scope="col" class="px-6 py-3">cpid</th>
              <th scope="col" class="px-6 py-3">Creator</th>
              <th scope="col" class="px-6 py-3">Divisible</th>
              <th scope="col" class="px-6 py-3">Locked</th>
              <th scope="col" class="px-6 py-3">Supply</th>
              <th scope="col" class="px-6 py-3">Keyburn</th>
              <th scope="col" class="px-6 py-3">Timestamp</th>
              <th scope="col" class="px-6 py-3">is_btc_stamp</th>
              <th scope="col" class="px-6 py-3">is_reissuance</th>
            </tr>
          </thead>
          <tbody>
            {issuances.map((issuance: StampRow) => {
              return (
                <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700">
                  <td class="px-6 py-4">
                    <Stamp stamp={issuance} />
                  </td>
                  <td class="px-6 py-4">{issuance.stamp}</td>
                  <td class="px-6 py-4 text-sm">{issuance.cpid}</td>
                  <td class="px-6 py-4 text-sm">
                    {issuance.creator_name ?? short_address(issuance.creator)}
                  </td>
                  <td class="px-6 py-4 text-sm">{issuance.divisible ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{issuance.locked ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{issuance.supply}</td>
                  <td class="px-6 py-4 text-sm">{issuance.keyburn ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{dayjs(Number(block_info.block_time) * 1000).fromNow()}</td>
                  <td class="px-6 py-4 text-sm">{issuance.is_btc_stamp ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{issuance.is_reissue ? "true" : "false"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
