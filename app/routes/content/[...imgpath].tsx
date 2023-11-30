import { HandlerContext } from "$fresh/server.ts";

export async function handler(
  req: Request,
  ctx: HandlerContext,
): Promise<Response> {
  const path = `../../static/stamp/${ctx.params.imgpath}`;
  try {
    const file = await Deno.readFile(path);
    return new Response(file, {
      status: 200,
      headers: {
        "Content-Type": "image/jpeg", // Asegúrate de ajustar el tipo de contenido según el tipo de archivo de imagen
      },
    });
  } catch (error) {
    console.error(error);
    return new Response("File not found", { status: 404 });
  }
}
