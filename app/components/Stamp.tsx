import { get_suffix_from_mimetype } from "$lib/utils/util.ts";
import { API_BASE } from "$lib/utils/constants.ts";

export const Stamp = ({ stamp }: { stamp: StampRow }) => {
  return (
    stamp.stamp_mimetype === "text/html"
      ? (
        <iframe
          width="100%"
          height="100%"
          class="w-24 h-24"
          style={{ imageRendering: "pixelated" }}
          src={`/content/${stamp.tx_hash}.${
            get_suffix_from_mimetype(stamp.stamp_mimetype)
          }`}
          onError={(e) => {
            e.currentTarget.src = stamp.stamp_url;
          }}
          alt="Stamp"
        />
      )
      : (
        <img
          class="w-16 h-16"
          style={{ imageRendering: "pixelated" }}
          src={`/content/${stamp.tx_hash}.${
            get_suffix_from_mimetype(stamp.stamp_mimetype)
          }`}
          onError={(e) => {
            console.log({e});
            e.currentTarget.src = `${API_BASE}/content/not-available.png`;
          }}
          alt="Stamp"
        />
      )
  );
};
export default Stamp;
