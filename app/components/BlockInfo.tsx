import dayjs from "$dayjs/";
import relativeTime from "$dayjs/plugin/relativeTime";

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
    <div class="border sm:p-1 relative overflow-x-auto shadow-lg sm:rounded-lg h-full flex flex-col justify-around gap-4">
      <BlockHeaderTable block={block} />
      <BlockIssuancesTable block={block} />
      <BlockSendsTable block={block} />
    </div>
  );
}
