import { get_suffix_from_mimetype } from "$lib/utils/util.ts";
import { BASE_URL } from "$lib/utils/constants.ts";

export const Stamp = ({ stamp }: { stamp: StampRow }) => {
  return (
    stamp.stamp_mimetype === "text/html" 
      ? (
        <iframe
          class="w-16 h-16"
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
      :
      !stamp.stamp_mimetype ? (
        <img
          class="w-16 h-16"
          style={{ imageRendering: "pixelated" }}
          src={`/content/not-available.png`}
          onError={(e) => {
            console.log({e});
            e.currentTarget.src = `/content/not-available.png`;
          }}
          alt="Stamp"
        />
      ) :
      (
        <img
          class="w-16 h-16"
          style={{ imageRendering: "pixelated" }}
          src={`${BASE_URL}/content/${stamp.tx_hash}.${
            get_suffix_from_mimetype(stamp.stamp_mimetype)
          }`}
          onError={(e) => {
            console.log({e});
            e.currentTarget.src = `/content/not-available.png`;
          }}
          alt="Stamp"
        />
      )
  );
};
export default Stamp;
