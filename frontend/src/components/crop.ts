/**
 * Where a picture's square portrait sits, and the badge's portrait frame around
 * it, as the crop dialog draws them. The server cuts the same boxes
 * (backend/src/horatio/pictures.py: square_box and portrait_box).
 */

/** A box in the picture's own pixels. */
export type Box = { left: number; top: number; width: number; height: number };

/** The square, as the API takes it: fractions of the picture's width and height. */
export type Crop = { x: number; y: number; size: number };

/** The badge's portrait is 4 wide by 5 high (1.6 × 2 in on a 3 × 5 in badge). */
export const PORTRAIT_RATIO = 5 / 4;

/** The smallest square allowed, as a share of the picture's shorter side. */
export const SMALLEST = 0.1;

/** The biggest square in the middle: where a new picture's crop starts. */
export function centred(width: number, height: number): Box {
  const side = Math.min(width, height);
  return { left: (width - side) / 2, top: (height - side) / 2, width: side, height: side };
}

/** A square of `side` at (left, top), kept inside the picture and not too small. */
export function square(width: number, height: number, left: number, top: number, side: number): Box {
  const largest = Math.min(width, height);
  const s = Math.min(Math.max(side, largest * SMALLEST), largest);
  return {
    left: Math.min(Math.max(left, 0), width - s),
    top: Math.min(Math.max(top, 0), height - s),
    width: s,
    height: s,
  };
}

/** Resize a square to `side`, keeping its centre where it was (as far as the picture allows). */
export function resized(width: number, height: number, box: Box, side: number): Box {
  const cx = box.left + box.width / 2;
  const cy = box.top + box.height / 2;
  const s = Math.min(Math.max(side, Math.min(width, height) * SMALLEST), Math.min(width, height));
  return square(width, height, cx - s / 2, cy - s / 2, s);
}

/**
 * The badge's portrait: a 4:5 frame as wide as the square and centred on it,
 * moved to stay inside the picture, and narrowed if the picture is too short.
 */
export function portraitFrame(width: number, height: number, box: Box): Box {
  let w = box.width;
  let h = box.width * PORTRAIT_RATIO;
  if (h > height) {
    h = height;
    w = height / PORTRAIT_RATIO;
  }
  const cx = box.left + box.width / 2;
  const cy = box.top + box.height / 2;
  return {
    left: Math.min(Math.max(cx - w / 2, 0), width - w),
    top: Math.min(Math.max(cy - h / 2, 0), height - h),
    width: w,
    height: h,
  };
}

export function toCrop(width: number, height: number, box: Box): Crop {
  return { x: box.left / width, y: box.top / height, size: box.width / width };
}

export function fromCrop(width: number, height: number, crop: Crop | null | undefined): Box {
  if (!crop) return centred(width, height);
  return square(width, height, crop.x * width, crop.y * height, crop.size * width);
}
