/** "p. 225" for the core book; a supplement's reference as given ("Vol. 2, p. 98"). */
export const pageText = (page: string) => (/^\d/.test(page) ? `p. ${page}` : page);
