import { render } from '/plugins/orbit_core/static/orbit.js';

export default async function (shadow, ctx) {
  await render(shadow, ctx, 'pass');
}
