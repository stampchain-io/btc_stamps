export const get_suffix_from_mimetype = (mimetype: string) => {
  const suffix = mimetype.split("/")[1];
  if (suffix === "jpeg") return "jpg";
  if (suffix === "svg+xml") return "svg";
  return suffix;
};
