import { get_suffix_from_mimetype } from "$lib/utils/util.ts";
import { BASE_URL } from "$lib/utils/constants.ts";

export const Stamp = ({ stamp }: { stamp: StampRow }) => {

  if (stamp.stamp_mimetype === "text/html") {
    return (
      <iframe
        class="w-16 h-16"
        src={`/content/${stamp.tx_hash}.${get_suffix_from_mimetype(stamp.stamp_mimetype)
          }`}
        onError={(e) => {
          e.currentTarget.src = stamp.stamp_url;
        }}
        alt="Stamp"
      />
    )
  };
  if (!stamp.stamp_mimetype) {
    return (
      <img
        class="w-16 h-16"
        style={{ imageRendering: "pixelated" }}
        src={`/content/not-available.png`}
        onError={(e) => {
          console.log({ e });
          e.currentTarget.src = `/content/not-available.png`;
        }}
        alt="Stamp"
      />
    )
  };
  return (
    <img
      class="w-16"
      style={{ imageRendering: "pixelated", objectFit: "contain" }}
      src={`/content/${stamp.tx_hash}.${get_suffix_from_mimetype(stamp.stamp_mimetype)
        }`}
      onError={(e) => {
        console.log({ e });
        e.currentTarget.src = `/content/not-available.png`;
      }}
      alt="Stamp"
    />
  )
};
export default Stamp;
