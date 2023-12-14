import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import Stamp from "$/components/Stamp.tsx";
import { StampKind } from "$/components/StampKind.tsx";

import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

dayjs.extend(relativeTime);

interface BlockIssuancesTableProps {
  block: {
    block_info: BlockInfo;
    issuances: StampRow[];
    sends: SendRow[];
  }
}

export default function BlockIssuancesTable(props: BlockIssuancesTableProps) {
  const { block_info, issuances } = props.block;

  return (
      <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
        <table class="w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
        <caption class="p-5 text-lg font-semibold text-left rtl:text-right text-gray-900 bg-white dark:text-white dark:bg-gray-800">
          Issuances
        </caption>
          <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              <th scope="col" class="px-6 py-3">Image</th>
              <th scope="col" class="px-6 py-3">Stamp</th>
              <th scope="col" class="px-6 py-3">Kind</th>
              <th scope="col" class="px-6 py-3">cpid</th>
              <th scope="col" class="px-6 py-3">Creator</th>
              <th scope="col" class="px-6 py-3">Divisible</th>
              <th scope="col" class="px-6 py-3">Locked</th>
              <th scope="col" class="px-6 py-3">Supply</th>
              <th scope="col" class="px-6 py-3">Keyburn</th>
              <th scope="col" class="px-6 py-3">Timestamp</th>
              <th scope="col" class="px-6 py-3">is_reissuance</th>
            </tr>
          </thead>
          <tbody>
            {issuances.map((issuance: StampRow) => {
              return (
                <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700">
                  <td class="px-0.5 py-0.5">
                    <Stamp stamp={issuance} />
                  </td>
                  <td class="px-6 py-4">{issuance.stamp >= 0 ? issuance.stamp : 'CURSED'}</td>
                  <td class="px-6 py-4 text-sm">
                    {
                    issuance.is_btc_stamp ?
                      <img src="/img/btc_stamp_white.svg" width="42px" />
                      :
                      issuance.cpid.startsWith("A") ?
                        <img  src="/img/cursed_white.svg" width="42px" />
                        :
                        <div class="flex flex-row gap-2">
                          <img  src="/img/cursed_white.svg" width="42px" />
                          <img  src="/img/named_white.svg" width="42px" />
                        </div>
                    }
                  </td>
                  <td class="px-6 py-4 text-sm">{issuance.cpid}</td>
                  <td class="px-6 py-4 text-sm">
                    {issuance.creator_name ?? short_address(issuance.creator)}
                  </td>
                  <td class="px-6 py-4 text-sm">{issuance.divisible ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{issuance.locked ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{issuance.supply}</td>
                  <td class="px-6 py-4 text-sm">{issuance.keyburn ? "true" : "false"}</td>
                  <td class="px-6 py-4 text-sm">{dayjs(Number(block_info.block_time) * 1000).fromNow()}</td>
                  <td class="px-6 py-4 text-sm">{issuance.is_reissue ? "true" : "false"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
  )
}