/** Where the V20 LARP SRD's pages are: the rules taken from it rather than a book (Dark Thaumaturgy) cite a link there. */
const SRD = "https://www.oneworldofdarkness.com/srd-v20/";
export const SRD_NAME = "V20 LARP SRD";

/** Whether a page reference is a link to a page of the V20 LARP SRD. */
export const isSrdPage = (page: string) => page.startsWith(SRD);

/** "p. 225" for the core book; a supplement's reference as given ("Vol. 2, p. 98"); the SRD's name for a link to it. */
export const pageText = (page: string) => (isSrdPage(page) ? SRD_NAME : /^\d/.test(page) ? `p. ${page}` : page);
