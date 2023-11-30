import { HandlerContext } from "$fresh/server.ts";
import { getMimeType } from "$lib/utils/util.ts";

export async function handler(
  req: Request,
  ctx: HandlerContext,
): Promise<Response> {
  const { imgpath } = ctx.params;
  const path = `../../static/stamp/${imgpath}`;
  try {
    const file = await Deno.readFile(path);

    const mimeType = getMimeType(imgpath.split(".").pop() as string);
    console.log(mimeType);
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
