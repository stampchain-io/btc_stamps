import { get_suffix_from_mimetype } from "$lib/utils/util.ts";

export const Stamp = ({ stamp }: { stamp: StampRow }) => {
  return (
    stamp.stamp_mimetype === "text/html"
      ? (
        <iframe
          width="100%"
          height="100%"
          class="w-24 h-24"
          data-fresh-disable-lock
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
          class="w-24 h-24"
          data-fresh-disable-lock
          style={{ imageRendering: "pixelated" }}
          src={`/content/${stamp.tx_hash}.${
            get_suffix_from_mimetype(stamp.stamp_mimetype)
          }`}
          onError={(e) => {
            e.currentTarget.src = "/content/not-available.png";
          }}
          alt="Stamp"
        />
      )
  );
};
export default Stamp;
