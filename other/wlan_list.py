
def print_wlan_list(sort_by=3, sort_desc=True):
	"""sort by 0 = network name, 1 = bssid, 2 = ch, 3 = signal, ..."""
	
	import network
	from ubinascii import hexlify


	wlan = network.WLAN(network.STA_IF)
	prev_wlan_state = wlan.active()  # restore after scan
	wlan.active(True)

	table_header = ("network name", "BSSID", "CH", "signal", "authmode", "visibility")


	# safe all networks as tuples in a list, where [0] is a list
	# containing the maximum lengths of the subitems for display;
	# - 0: network name
	# - 1: bssid (hardware address)
	# - 2: channel
	# - 3: rssi (signal strength, the higher the better)
	# - 4: authmode (most likely WPA/WPA2-PSK)
	# - 5: visible/hidden
	scan = [[0]*len(table_header)]

	# minimum length is table header
	for i in range(len(table_header)):
		scan[0][i] = len(table_header[i])

	# scan
	for item in wlan.scan():
		bssid = hexlify(item[1]).decode("ascii")
		bssid = ':'.join([bssid[i:i+2] for i in range(0, len(bssid), 2)])
		
		new = (item[0].decode("utf-8"),
			   bssid,
			   item[2],
			   item[3],
			   ("open", "WEP", "WPA-PSK", "WPA2-PSK", "WPA/WPA2-PSK")[int(item[4])],
			   ("visible", "hidden")[int(item[5])])
		scan.append(new)
		
		for i in range(0, len(scan[0])):
			len_new = len(str(new[i]))
			if len_new > scan[0][i]:
				scan[0][i] = len_new
	
	wlan.active(prev_wlan_state)
	

	# print table
	def center_subitems(ituple):
		retlist = []
		for i in range(len(ituple)):
			missing_spaces = scan[0][i] - len(str(ituple[i]))
			if missing_spaces > 0:
				spaces_right = int(missing_spaces/2)
				spaces_left = missing_spaces - spaces_right
				retlist.append(' '*spaces_left + str(ituple[i]) + ' '*spaces_right)
			else:
				retlist.append(ituple[i])
		return tuple(retlist)
		
	header_string = "|| %s || %s | %s | %s | %s | %s ||" % center_subitems(table_header)
	print('-'*len(header_string))
	print(header_string)
	print('-'*len(header_string))

	for item in sorted(scan[1:], key=lambda x: x[sort_by], reverse=sort_desc):
		print("|| %s || %s | %s | %s | %s | %s ||" % center_subitems(item))

	print('-'*len(header_string))
	
	
if __name__ == "__main__":
	print_wlan_list()