interface BlockInfoProps {
  block: Signal<BlockRow>;
}

export default function BlockInfo (props) {
  const { block } = props;

  return (
    <div class="mt-8 text-center">
      <div class="text-2xl text-[#ffffff]">{block.value.block_index}</div>
      <div class="text-[#ffffff] py-2 text-lg">
        {
          `${block.value.block_hash.substring(0, 10)}...${block.value.block_hash.substring(block.value.block_hash.length - 10, block.value.block_hash.length)}`
        }
      </div>
    </div>
  )
}
