import { get_suffix_from_mimetype, short_address } from "$lib/utils/util.ts";

interface BlockInfoProps {
  block: BlockInfo;
}

export default function BlockInfo(props: BlockInfoProps) {
  const { block } = props;
  const { block_info, data: issuances } = block;
  const time = new Date(Number(block_info.block_time) * 1000);

  return (
    <div class="mt-8 text-center p-4 w-full mx-auto">
      <table class="table-auto w-full text-white text-left mb-4 border">
        <tbody>
          <tr>
            <th>Block Hash</th>
            <td>{block_info.block_hash}</td>
          </tr>
          <tr>
            <th>Time</th>
            <td>{time.toLocaleString()}</td>
          </tr>
          <tr>
            <th>Height</th>
            <td>{block_info.block_index}</td>
          </tr>
          <tr>
            <th>Issuances</th>
            <td>{issuances.length}</td>
          </tr>
        </tbody>
      </table>
      <div class="text-2xl text-[#ffffff]">
        <h2>Issuances</h2>
      </div>

      <table class="table-auto w-full text-white responsive-table border">
        <thead class="border-b">
          <tr>
            <th>Image</th>
            <th>Stamp</th>
            <th>cpid</th>
            <th>Creator</th>
            <th>Divisible</th>
            <th>Locked</th>
            <th>Supply</th>
            <th>Keyburn</th>
            <th>Timestamp</th>
            <th>is_btc_stamp</th>
            <th>is_reissuance</th>
          </tr>
        </thead>
        <tbody>
          {issuances.map((issuance: StampRow) => {
            return (
              <tr>
                <td>
                  <img
                    class="w-24 h-24"
                    data-fresh-disable-lock
                    style={{ imageRendering: "pixelated" }}
                    src={`/stamps/${issuance.tx_hash}.${
                      get_suffix_from_mimetype(issuance.stamp_mimetype)
                    }`}
                    alt="Stamp"
                  />
                </td>
                <td>{issuance.stamp}</td>
                <td class="text-sm">{issuance.cpid}</td>
                <td class="text-sm">
                  {issuance.creator_name ?? short_address(issuance.creator)}
                </td>
                <td>{issuance.divisible ? "true" : "false"}</td>
                <td>{issuance.locked ? "true" : "false"}</td>
                <td>{issuance.supply}</td>
                <td>{issuance.keyburn ? "true" : "false"}</td>
                <td>{new Date(issuance.timestamp).toLocaleDateString()}</td>
                <td>{issuance.is_btc_stamp ? "true" : "false"}</td>
                <td>{issuance.is_reissue ? "true" : "false"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
