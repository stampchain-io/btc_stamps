import { HandlerContext } from "$fresh/server.ts";
import { getMimeType } from "$lib/utils/util.ts";

export async function handler(
  req: Request,
  ctx: HandlerContext,
): Promise<Response> {
  const { imgpath } = ctx.params;
  let path;
  if (imgpath === "not-available.png") {
    path = `${Deno.cwd()}/static/${imgpath}`;
  } else {
    path = `${Deno.cwd()}/static/stamps/${imgpath}`;
  }
  try {
    const file = await Deno.readFile(path);
    const mimeType = getMimeType(imgpath.split(".").pop() as string);
    return new Response(file, {
      status: 200,
      headers: {
        "Content-Type": mimeType,
      },
    });
  } catch (error) {
    console.error(error);
    return new Response("File not found", { status: 404 });
  }
}
