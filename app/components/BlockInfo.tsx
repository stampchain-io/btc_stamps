import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";
import BlockHeaderTable from "$/components/BlockHeaderTable.tsx";
import BlockIssuancesTable from "$/components/BlockIssuancesTable.tsx";
import BlockSendsTable from "$/components/BlockSendsTable.tsx";

dayjs.extend(relativeTime);

interface BlockInfoProps {
  block: BlockInfo;
}

export default function BlockInfo(props: BlockInfoProps) {
  const { block } = props;
  const { block_info, issuances, sends } = block;
  
  return (
    <div class="border sm:p-1 relative overflow-x-auto shadow-md sm:rounded-lg">
      <BlockHeaderTable block={block} />
      <div class="text-2xl p-2 text-[#ffffff]">
        <h2>Issuances</h2>
      </div>
      <BlockIssuancesTable block={block} />
      <div class="text-2xl p-2 text-[#ffffff]">
        <h2>Sends</h2>
      </div>
      <BlockSendsTable block={block} />
    </div>
  );
}
