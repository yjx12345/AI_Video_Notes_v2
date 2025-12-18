export const formatDate = (str) => {
  if (!str) return '';
  const d = new Date(str);
  const pad = (n) => n.toString().padStart(2, '0');
  return `${d.getMonth()+1}-${d.getDate()} ${d.getHours()}:${pad(d.getMinutes())}`;
};