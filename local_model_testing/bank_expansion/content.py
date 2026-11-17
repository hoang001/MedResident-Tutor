"""Manual source comparison by Codex, 2026-11-16. No model generation endpoint.

Each tuple holds the answer/criterion and the exact page paragraph anchors read
by the author. These are source-scoped educational questions, not clinical advice.
"""

TOPICS = {
    'open': 'Gãy xương hở', 'general': 'Liền xương và điều trị bảo tồn',
    'soft': 'Vết thương phần mềm', 'compartment': 'Chèn ép khoang',
    'shoulder': 'Trật khớp vai', 'elbow': 'Trật khớp khuỷu',
    'forearm': 'Cẳng tay và đầu dưới xương quay', 'hip': 'Trật khớp háng',
    'neck': 'Gãy cổ xương đùi', 'spine': 'Chấn thương cột sống',
}

# (topic, objective, question, [(criterion/reference sentence, [(PDF page, anchors)])], optional original book question index)
ITEMS = []
def add(topic, objective, question, criteria, book=None):
    ITEMS.append(dict(topic=topic, objective=objective, question=question, criteria=criteria, book=book))

add('general', 'pathologic-fatigue', 'Phân biệt gãy xương bệnh lý và gãy xương do mỏi về nền xương và cơ chế gây gãy.', [
 ('Gãy bệnh lý xảy ra tự nhiên hoặc sau chấn thương nhẹ trên xương đã bị bệnh làm yếu hoặc phá hủy.', [(9, ['Xương gãy tự nhiên'])]),
 ('Gãy do mỏi là hậu quả lực nhỏ lặp lại nhiều lần, kéo dài tại cùng vị trí; có thể gặp ở xương chi dưới khi đi bộ nhiều.', [(9, ['Lực chấn thương tuy nhỏ'])]),
])
add('general', 'hairline-greenstick', 'Phân biệt gãy rạn và gãy cành tươi; khi nghi gãy rạn nhưng phim ban đầu chưa rõ, tài liệu nêu cách kiểm tra nào?', [
 ('Gãy rạn có đường nứt nhỏ, đôi khi khó thấy trên phim X-quang ban đầu.', [(9, ['rạn'])]),
 ('Gãy cành tươi chỉ gãy một phía vỏ xương, phía đối diện còn liên tục nhưng bị uốn cong gây gấp góc.', [(9, ['cành tươi'])]),
 ('Có thể chụp thêm tư thế chéo, kiểm tra chất lượng phim, chụp lại sau 7–10 ngày hoặc dùng cắt lớp vi tính khi cần.', [(9, ['Gãy rạn'])]),
])
add('general', 'callus-xray', 'Mô tả ba mức độ can xương trên X-quang được phần liền xương của tài liệu nêu.', [
 ('Độ I: can mờ, khe gãy vẫn rõ.', [(12, ['độ I', 'Độ I'])]),
 ('Độ II: can tạo cầu nối nhưng vẫn còn thấy khe gãy.', [(12, ['độ II', 'Độ II'])]),
 ('Độ III: can vững chắc và không còn thấy khe gãy.', [(12, ['độ III', 'Độ III'])]),
])
add('general', 'consolidation-remodelling', 'Phân biệt giai đoạn củng cố với giai đoạn sửa chữa hình thể trong liền xương.', [
 ('Củng cố (Consolidation) là quá trình tổ chức lại các lá xương theo hướng tác động của lực cơ học.', [(12, ['Consolidation'])]),
 ('Sửa chữa hình thể tái lập hình dạng xương và ống tủy; khả năng này ở trẻ em tốt hơn người lớn.', [(12, ['hình thể'])]),
])
add('general', 'healing-factors', 'Nêu các nhóm yếu tố thuận lợi và bất lợi cho liền xương, xét cả tại chỗ và người bệnh.', [
 ('Tại chỗ thuận lợi khi tưới máu tốt, ít tổn thương phần mềm, nắn chỉnh đúng và cố định vững; xương xốp thường liền thuận lợi.', [(13, ['giàu mạch', 'Xương dẹt', 'phần mềm hạn chế', 'đúng giải phẫu', 'bất động tốt'])]),
 ('Gãy phức tạp, mất xương, tổn thương phần mềm nặng, nhiễm trùng, kém tưới máu hoặc cố định không tốt làm chậm liền.', [(13, ['mảnh rời', 'nhiều đoạn', 'phần mềm nặng', 'khuyết xương', 'bất động không', 'Nhiễm trùng', 'nghèo mạch'])]),
 ('Người trẻ khỏe liền thuận lợi hơn; tuổi cao, bệnh phối hợp, hút thuốc và uống rượu là các yếu tố bất lợi được nêu.', [(13, ['tuổi', 'rượu', 'thuốc'])]),
])
add('general', 'fracture-imaging', 'Khi chụp X-quang gãy thân xương dài, cần lấy phạm vi và tư thế nào? Khi nào cân nhắc CT, MRI hoặc Doppler?', [
 ('X-quang cần ít nhất hai bình diện thẳng và nghiêng, lấy cả khớp trên và khớp dưới ổ gãy.', [(14, ['Trên phim X quang'])]),
 ('CT hoặc MRI hỗ trợ các trường hợp khó xác định như gãy kín đáo hoặc gãy bệnh lý; Doppler khi nghi tổn thương mạch.', [(14, ['cắt lớp', 'Doppler'])]),
])
add('general', 'cast-materials', 'So sánh bột thạch cao và bột thủy tinh về khả năng tạo khuôn, thời gian cứng và việc tháo bỏ.', [
 ('Thạch cao dễ tạo khuôn và tháo bỏ nhưng dễ hỏng khi ướt, nặng và cần thời gian đông cứng trước chịu lực.', [(16, ['thạch cao'])]),
 ('Bột thủy tinh nhẹ, cứng nhanh hơn nhưng khó tạo khuôn và khó tháo hơn.', [(16, ['thủy tinh'])]),
])
add('general', 'cast-padding', 'Trong bó bột, lớp tất lót và lớp bông có tác dụng gì; cần chú ý ở các điểm xương nhô?', [
 ('Tất lót bảo vệ da, thấm mồ hôi, giảm trầy xước và được gấp ở mép bột để tránh cạnh sắc cọ da.', [(18, ['tất'])]),
 ('Bông phân bố áp lực; cần đệm kỹ tại các điểm xương nhô và dự kiến sưng nề.', [(18, ['bông'])]),
])
add('general', 'early-cast-swelling', 'Trước khi bó bột chi vừa bị gãy còn có nguy cơ sưng nề, cần chú ý đồ trang sức và cách xử lý bột giai đoạn đầu như thế nào?', [
 ('Tháo nhẫn và đồ trang sức ở chi trước khi bó, tránh chèn ép khi sưng.', [(19, ['nhẫn', 'trang sức'])]),
 ('Bột trong giai đoạn đầu nên được rạch dọc để dự phòng chèn ép; khi hết sưng đánh giá lại và thay bột phù hợp.', [(19, ['rạch', '7'])]),
])
add('general', 'temporary-splint', 'Vì sao nẹp bột phù hợp cho bất động tạm thời ở chi sưng nề hoặc tổn thương phần mềm nhiều? Phạm vi bất động cần đạt là gì?', [
 ('Nẹp bột cho phép theo dõi phần mềm và mạch máu thuận lợi hơn, phù hợp khi chi còn sưng hoặc cần theo dõi.', [(20, ['nẹp'])]),
 ('Nẹp phải đủ dài để bất động khớp trên và khớp dưới ổ gãy.', [(20, ['khớp'])]),
])
add('general', 'cast-pressure-warning', 'Những triệu chứng nào sau bó bột gợi ý chèn ép cần được phát hiện sớm? Nêu cả biểu hiện cảm giác và tuần hoàn, vận động.', [
 ('Đau hoặc căng tức tăng, tê bì, bỏng rát là các dấu hiệu cảnh báo.', [(20, ['Chèn ép', 'chèn ép'])]),
 ('Các ngón sưng, tím hoặc lạnh, vận động giảm là dấu hiệu cần đánh giá ngay, không coi là khó chịu bình thường do bột.', [(20, ['ngón', 'tím'])]),
])
add('general', 'cast-local-troubles', 'Phân biệt dấu hiệu gợi ý loét tỳ đè dưới bột với dấu hiệu bột bị lỏng và hậu quả của bột lỏng.', [
 ('Loét tỳ đè có thể gây đau khu trú, thấm dịch hoặc mùi hôi; nhiễm trùng có thể kèm sốt.', [(20, ['loét', 'Loét'])]),
 ('Bột lỏng cho phép chi di động trong khuôn, làm giảm hiệu quả bất động và có nguy cơ di lệch thứ phát; cần đánh giá thay bột.', [(20, ['lỏng'])]),
])

add('soft', 'avulsion-perfusion', 'Vì sao vạt da bong lóc sau tai nạn có thể hoại tử dù vẫn còn cuống nối với phần da lành?', [
 ('Mạch nuôi đi từ lớp sâu lên da có thể đã đứt khi bong lóc, nên còn cuống da không đồng nghĩa còn cấp máu đầy đủ.', [(91, ['mạch máu', 'bong lóc'])]),
 ('Diện bong lóc rộng có tiên lượng nặng; phải đánh giá tưới máu và nguy cơ hoại tử thay vì chỉ nhìn tính liên tục của da.', [(92, ['Bong lóc'])]),
])
add('soft', 'morphology', 'Phân biệt vết thương xây sát, rách cắt và xuyên thủng còn dị vật về hình thái tổn thương.', [
 ('Xây sát nông ở thượng bì; nếu chưa qua lớp tế bào đáy có thể tự liền và ít sẹo.', [(92, ['Xây sát'])]),
 ('Rách cắt làm gián đoạn các lớp da, cân hoặc cơ.', [(92, ['Rách cắt'])]),
 ('Vết xuyên có đường đi qua mô; loại còn dị vật vẫn có tác nhân mắc kẹt ở nông hoặc sâu, cần nhận diện đường đi và dị vật.', [(92, ['Xuyên thủng', 'Còn dị vật'])]),
])
add('soft', 'sharp-highenergy', 'So sánh vết thương do vật sắc cắt với vết thương do lực trực tiếp năng lượng cao; vì sao mép sắc gọn vẫn cần khám kỹ?', [
 ('Vật sắc thường tạo bờ gọn, tổn thương theo đường đi nhưng có thể sâu, cắt gân, mạch hoặc thần kinh và còn mảnh kính.', [(93, ['cơ chế bị cắt'])]),
 ('Lực năng lượng cao thường gây dập nát phức tạp, nhiều dị vật, có thể gãy hở và nguy cơ nhiễm khuẩn cao.', [(93, ['năng lượng cao'])]),
])
add('soft', 'wound-history', 'Trước một vết thương phần mềm, cần hỏi những nhóm thông tin nào để đánh giá nguy cơ và quá trình xử trí?', [
 ('Hỏi tuổi, thể trạng, nghề nghiệp, bệnh nền và cơ chế tai nạn.', [(94, ['Đặc điểm bệnh nhân', 'Nguyên nhân'])]),
 ('Hỏi môi trường ô nhiễm, thời gian từ tai nạn tới xử trí và các biện pháp sơ cứu hoặc điều trị tuyến trước.', [(94, ['Mức độ ô nhiễm', 'Thời gian', 'Các biện pháp'])]),
])
add('soft', 'exam-recording', 'Mô tả những nội dung cần ghi khi khám tại chỗ vết thương phần mềm và cách tránh bỏ sót tổn thương.', [
 ('Ghi vị trí, số lượng, kích thước; kiểm tra vùng bị quần áo hoặc nếp gấp che lấp.', [(94, ['Vị trí'])]),
 ('Ghi mép, hướng, da xung quanh, mức ô nhiễm, dị vật và các cấu trúc lộ ra; xác định cả đường vào, đường ra nếu xuyên.', [(94, ['Đặc điểm mép']), (95, ['Đặc điểm miệng'])]),
 ('Khám chức năng gân, vận động, cảm giác và tưới máu ngọn chi để nhận diện tổn thương cấu trúc đi qua vùng thương tổn.', [(95, ['Đánh giá các thương tổn'])]),
])
add('soft', 'wound-imaging', 'Nêu vai trò khác nhau của X-quang, CT và Doppler hoặc DSA khi đánh giá vết thương phần mềm.', [
 ('X-quang phát hiện gãy xương phối hợp và có thể gợi ý thấu khớp qua bóng khí trong khớp.', [(95, ['Dùng để chẩn đoán'])]),
 ('CT đánh giá tổn thương xương, thấu khớp và dị vật sâu.', [(95, ['Tương tự X quang'])]),
 ('Doppler hoặc DSA đánh giá khi nghi tổn thương động mạch lớn.', [(95, ['Có giá trị'])]),
])
add('soft', 'crp-lactate', 'Trong tổn thương phần mềm lớn, CRP tăng có chứng minh riêng nhiễm trùng không? Lactat tăng liên tục gợi ý điều gì theo tài liệu?', [
 ('CRP phản ánh đáp ứng viêm nhưng không phân biệt riêng viêm với nhiễm trùng.', [(95, ['Protein phản ứng C'])]),
 ('Lactat phản ánh thiếu oxy tế bào và chuyển hóa yếm khí; cao và tiếp tục tăng là dấu hiệu tiên lượng xấu, gợi ý nguy cơ suy đa tạng.', [(95, ['Lactat'])]),
])
add('soft', 'graft-flap', 'Phân biệt cơ chế nuôi dưỡng của mảnh ghép da rời với vạt có cuống; nền nhận ghép cần những điều kiện gì?', [
 ('Mảnh ghép da rời không mang cuống mạch, giai đoạn đầu được nuôi qua nền nhận bằng thẩm thấu; vạt có cuống duy trì nguồn cấp máu qua cuống.', [(10, ['thẩm thấu', 'cuống'])]),
 ('Nền nhận cần sạch, tổ chức hạt tốt, không bẩn hoặc phù nề và người bệnh có điều kiện dinh dưỡng thích hợp để ghép sống.', [(10, ['Muốn miếng da sống tốt'])]),
])
add('soft', 'late-wound-sequelae', 'Nêu các cơ chế dẫn tới nhiễm khuẩn thứ phát, hoại tử vạt và hạn chế vận động sau xử lý vết thương phần mềm.', [
 ('Cắt lọc không hết, không kiểm soát đáy, khâu quá kín hoặc để khoảng chết tạo nguy cơ nhiễm khuẩn thứ phát.', [(100, ['Nhiễm khuẩn thứ phát'])]),
 ('Vạt thiếu nuôi dưỡng, khâu căng hoặc xử lý bong lóc không tốt dễ hoại tử và tạo nơi nhiễm khuẩn thứ phát.', [(100, ['Hoại tử vạt da'])]),
 ('Sẹo co kéo, mất nhiều mô mềm và bất động dài có thể gây co rút, hạn chế vận động.', [(100, ['Sẹo co kéo'])]),
])

add('compartment', 'forms', 'Phân biệt hội chứng chèn ép khoang cấp tính, dạng liên quan gắng sức và co rút Volkmann.', [
 ('Dạng cấp tính tăng áp lực nhanh, giảm tưới máu, có thể hoại tử mô nếu không xử trí kịp.', [(55, ['cấp tính'])]),
 ('Dạng gắng sức xuất hiện đau khi vận động và có thể giảm khi nghỉ; tiếp tục gắng sức có thể tiến triển nặng.', [(55, ['gắng sức'])]),
 ('Volkmann là hậu quả muộn: cơ thiếu máu hoại tử rồi xơ hóa, gây co rút không hồi phục.', [(55, ['Volkmann'])]),
])
add('compartment', 'volume-causes', 'Phân nhóm nguyên nhân chèn ép khoang thành tăng thể tích bên trong và giảm dung tích khoang; cho ví dụ mỗi nhóm.', [
 ('Tăng thể tích bên trong do máu tụ sau gãy xương, dập cơ, rối loạn đông máu hoặc phù sau tái tưới máu.', [(56, ['gãy', 'máu', 'tái'])]),
 ('Giảm dung tích do bó bột hoặc băng quá chặt, đóng cân căng, bỏng làm vỏ khoang hạn chế giãn.', [(56, ['bột', 'băng', 'bỏng'])]),
])
add('compartment', 'perfusion-mechanism', 'Giải thích vòng xoắn bệnh lý làm giảm tưới máu trong chèn ép khoang. Vì sao vẫn có thể còn mạch ngoại vi?', [
 ('Áp lực mô tăng làm tăng áp lực tĩnh mạch, giảm chênh áp động–tĩnh mạch và giảm lưu lượng tưới máu cơ.', [(57, ['Áp lực trong tĩnh mạch'])]),
 ('Vi tuần hoàn và thần kinh bị ảnh hưởng sớm hơn động mạch lớn; do đó bắt được mạch ngoại vi không loại trừ chèn ép khoang.', [(57, ['thần kinh', 'mạch'])]),
], book=6)
add('compartment', 'early-late', 'Nêu các dấu hiệu sớm và các dấu hiệu muộn của chèn ép khoang; có nên đợi mất mạch mới nghi ngờ không?', [
 ('Sớm: đau quá mức tổn thương, đau tăng khi kéo căng thụ động, khoang căng và rối loạn cảm giác.', [(58, ['đau', 'Đau', 'cảm giác'])]),
 ('Muộn: da tái lạnh, tưới máu đầu chi giảm, liệt hoặc mất mạch; không đợi các dấu hiệu muộn mới nghi ngờ.', [(58, ['muộn', 'mạch'])]),
])
add('compartment', 'missed-diagnosis', 'Những hoàn cảnh nào khiến biểu hiện chèn ép khoang khó được phát hiện? Gãy hở nặng có loại trừ hội chứng này không?', [
 ('Đa chấn thương, chấn thương sọ não hoặc giảm ý thức, tổn thương thần kinh, gây tê vùng và dùng giảm đau có thể che lấp triệu chứng.', [(57, ['sọ não', 'gây tê', 'giảm đau'])]),
 ('Gãy hở kể cả độ III không loại trừ chèn ép khoang; không được coi vết thương hở là giải áp đầy đủ mọi khoang.', [(56, ['gãy hở'])]),
])
add('compartment', 'diagnostic-tools', 'Vì sao cần diễn giải áp lực khoang cùng huyết áp? Doppler hoặc chụp mạch có thay thế đánh giá chèn ép khoang không?', [
 ('Tưới máu phụ thuộc chênh lệch huyết áp tâm trương với áp lực khoang; cùng áp lực khoang, hạ huyết áp làm tưới máu kém hơn.', [(58, ['huyết áp']), (59, ['tâm trương'])]),
 ('Doppler hoặc chụp mạch giúp đánh giá tổn thương mạch lớn hoặc chẩn đoán phân biệt; không thay thế khám, theo dõi và đánh giá áp lực khoang khi cần.', [(59, ['Doppler', 'mạch'])]),
])
add('compartment', 'fasciotomy-principles', 'Nêu các nguyên tắc chung của mở cân giải ép khoang cấp tính, không yêu cầu mô tả đường rạch từng chi.', [
 ('Giải phóng đầy đủ mọi khoang liên quan, mở đủ chiều dài; không chỉ rạch cân dưới da trong chèn ép khoang cấp.', [(61, ['khoang', 'dưới da'])]),
 ('Đánh giá tưới máu và sức sống cơ, lấy máu tụ và cắt lọc cơ hoại tử khi cần, đồng thời bảo vệ mạch thần kinh.', [(61, ['cơ', 'máu'])]),
])
add('compartment', 'leg-compartments', 'Cẳng chân có những khoang cơ nào và hai đường mở thường dùng tiếp cận các khoang đó ra sao?', [
 ('Bốn khoang: trước, ngoài, sau nông và sau sâu.', [(61, ['khoang'])]),
 ('Đường trước ngoài giải phóng khoang trước và ngoài; đường trong giải phóng khoang sau nông và sau sâu, chú ý bảo vệ mạch thần kinh.', [(61, ['ngoài', 'trong'])]),
])
add('compartment', 'post-release-followup', 'Sau giải ép khoang, cần theo dõi vết thương, sức sống cơ và những hậu quả tại chỗ hoặc toàn thân nào?', [
 ('Vết mổ thường để hở, che phủ ẩm và đánh giá lại sức sống cơ; cơ hoại tử còn lại có thể cần cắt lọc thêm trước đóng hoặc ghép da.', [(64, ['48', 'hở', 'hoại tử'])]),
 ('Theo dõi hoại tử cơ, mất chức năng, co rút Volkmann hoặc phải cắt cụt khi tổn thương nặng; tái tưới máu có thể gây biến chứng toàn thân, suy đa tạng.', [(65, ['Volkmann', 'tạng', 'cắt cụt']), (58, ['tái tưới máu'])]),
])

add('shoulder', 'definition-frequency', 'Định nghĩa trật khớp vai và trật vai tái diễn; phân biệt hướng trật với tần suất trật.', [
 ('Trật khớp vai là mất tiếp xúc giữa diện khớp ổ chảo và chỏm xương cánh tay.', [(254, ['Trật khớp vai là'])]),
 ('Tái diễn là trật cùng bên từ lần thứ hai trở lên; ra trước, ra sau, lên trên hoặc xuống dưới là hướng trật, không phải số lần trật.', [(254, ['Về tần suất']), (258, ['Theo hướng'])]),
])
add('shoulder', 'stabilizers', 'Trình bày đặc điểm giải phẫu các hệ thống giữ khớp vai.', [
 ('Hệ tĩnh gồm sự toàn vẹn ổ chảo và chỏm, hình thể xương bả vai, áp lực âm và dịch khớp; bao khớp, dây chằng, sụn viền và các mốc xương góp phần chống trật.', [(255, ['toàn vẹn', 'áp lực', 'Góc nghiêng', 'dây chằng', 'Sụn viền', 'Mõm'])]),
 ('Hệ động gồm chóp xoay, đầu dài gân nhị đầu và các cơ cố định xương bả vai.', [(255, ['Đầu dài', 'Chóp xoay', 'Các cơ giữ'])]),
 ('Chỏm lớn, ổ chảo nông cho biên độ lớn nhưng kém vững; các hệ thống phải phối hợp để giữ khớp.', [(254, ['Khớp vai là'])]),
], book=118)
add('shoulder', 'anterior-posterior-mechanism', 'So sánh tư thế chi và cơ chế thường gây trật khớp vai ra trước với ra sau.', [
 ('Trật ra trước thường gián tiếp do ngã chống tay hoặc khuỷu khi tay dạng, đưa ra sau và xoay ngoài; cũng có thể do lực trực tiếp từ sau.', [(256, ['Cơ chế chấn thương'])]),
 ('Trật ra sau thường xảy ra khi cánh tay gấp, khép và xoay trong.', [(256, ['Cơ chế chấn thương'])]),
])
add('shoulder', 'bankart-hillsachs', 'Phân biệt tổn thương Bankart phần mềm, Bankart xương và Hill–Sachs trong trật khớp vai.', [
 ('Bankart liên quan bóc tách phức hợp sụn viền, dây chằng phía trước dưới ổ chảo; Bankart xương kèm mảnh vỡ bờ ổ chảo.', [(256, ['Tổn thương Bankart là', 'Bankart xương'])]),
 ('Hill–Sachs là khuyết hoặc lún diện khớp sau ngoài chỏm xương cánh tay do va vào bờ trước ổ chảo khi trật.', [(256, ['Đây là tổn thương'])]),
])
add('shoulder', 'acute-anterior-signs', 'Nêu các dấu hiệu tại chỗ gợi ý trật khớp vai cấp ra trước, từ tư thế tay đến hình dạng vai và dấu hiệu lò xo.', [
 ('Đau, hạn chế hoặc mất vận động; tay lành thường đỡ tay đau, vai vuông hoặc gù vai, mất hình dạng tròn bình thường.', [(258, ['Đối với trật vai cấp tính', 'Bệnh nhân đến khám'])]),
 ('Cánh tay dạng và xoay ngoài, khuỷu rời thân; ép vào thân rồi thả có kháng cự đàn hồi hoặc dấu lò xo, có thể sờ chỏm ở vị trí bất thường.', [(258, ['Bệnh nhân đến khám'])]),
])
add('shoulder', 'recurrent-history', 'Ở người có trật vai nhiều lần, cần khai thác những thông tin bệnh sử nào để đánh giá mất vững và lựa chọn điều trị?', [
 ('Hỏi lần trật đầu, các lần tiếp theo, tần suất, hoàn cảnh trật và khả năng tự nắn.', [(258, ['Còn đối với'])]),
 ('Hỏi tuổi, tay thuận, nghề nghiệp, mức hoạt động, cơ chế chấn thương, bệnh thần kinh cơ và lỏng lẻo các khớp khác.', [(258, ['Còn đối với'])]),
])
add('shoulder', 'instability-tests', 'Nêu mục đích của nghiệm pháp ngăn kéo, nghiệm pháp e sợ và dấu kéo giãn trong đánh giá mất vững vai tái diễn.', [
 ('Ngăn kéo đánh giá độ di chuyển trước sau và độ vững của chỏm trên ổ chảo; đau hoặc e sợ gợi ý mất vững.', [(258, ['Xác định mức độ']), (259, ['điểm dừng'])]),
 ('Nghiệm pháp e sợ đánh giá mất vững trước bằng tư thế dạng và xoay ngoài gây cảm giác sợ trật.', [(259, ['Đánh giá tình trạng'])]),
 ('Dấu kéo giãn đánh giá lỏng bao khớp phía dưới qua rãnh giữa mỏm cùng và đầu trên cánh tay; phải diễn giải cùng đau hoặc e sợ.', [(259, ['Được sử dụng'])]),
])
add('shoulder', 'imaging-roles', 'Trong trật vai, CT và MRI bổ sung thông tin gì khác nhau? Nêu các tư thế X-quang thường dùng.', [
 ('X-quang thường dùng trước sau, Y view; các tư thế West point và Stryker notch hỗ trợ đánh giá ổ chảo và chỏm.', [(260, ['Chụp X quang'])]),
 ('CT đánh giá hình thái tổn thương xương ba chiều; MRI đánh giá thêm sụn viền, dây chằng, bao khớp và chóp xoay.', [(260, ['Chụp CLVT'])]),
])
add('shoulder', 'post-reduction-neurovascular', 'Sau nắn trật vai, cần kiểm tra gì để phát hiện tổn thương thần kinh nách và động mạch nách?', [
 ('Kiểm tra cảm giác vùng delta hoặc mỏm vai và khả năng co cơ delta, dạng cánh tay để đánh giá thần kinh nách.', [(261, ['Gặp khoảng'])]),
 ('Kiểm tra mạch và tưới máu sau nắn; khi nghi tổn thương mạch cần đánh giá mạch bằng phương tiện thích hợp, vì có thể có rách, co thắt hoặc tổn thương nội mạc gây tắc.', [(261, ['Có khoảng'])]),
])
add('shoulder', 'repair-principles', 'Phân biệt mục tiêu phục hồi giải phẫu của phẫu thuật Bankart và Latarjet, không yêu cầu mô tả kỹ thuật đặt neo hay vít.', [
 ('Bankart phục hồi sụn viền hoặc phức hợp sụn viền bao khớp trước bị tổn thương bằng khâu về bờ ổ chảo, có thể kết hợp làm ngắn bao khớp.', [(265, ['Là phẫu thuật', 'Sau khi mở']), (266, ['Tiến hành khâu'])]),
 ('Latarjet chuyển mỏm quạ cùng các gân bám tới bờ trước dưới ổ chảo để bổ sung phần khuyết xương và tăng vững.', [(267, ['Đây là phẫu thuật'])]),
])

add('elbow', 'mechanism-pathology', 'Trình bày cơ chế chấn thương và tổn thương giải phẫu bệnh trong trật khớp khuỷu.', [
 ('Trật sau thường do ngã chống tay khi khuỷu duỗi gây quá duỗi; trật trước do lực đánh vào phía sau khuỷu khi tay gấp.', [(313, ['Trật khớp khuỷu ra sau:', 'Trật khớp khuỷu ra trước:'])]),
 ('Bao khớp và các dây chằng bị rách hoặc đứt; có thể phối hợp vỡ đầu dưới cánh tay, mỏm vẹt hoặc mỏm khuỷu.', [(313, ['Có thể gặp tổn thương']), (314, ['Các dây chằng'])]),
 ('Có thể tổn thương động mạch cánh tay và thần kinh vùng khuỷu như giữa, trụ, quay.', [(314, ['Có thể tổn thương'])]),
], book=11)
add('elbow', 'classification', 'Trình bày phân loại trật khớp khuỷu.', [
 ('Theo hướng: ra sau thường gặp nhất, ra trước hiếm, sang bên thường đi kèm trật sau hoặc gãy xương.', [(314, ['Trật khớp khuỷu ra sau:', 'Trật khớp khuỷu ra trước:', 'Trật khớp khuỷu sang bên:'])]),
 ('Theo thời gian trong giáo trình: mới dưới 3 tuần và cũ trên 3 tuần; trường hợp đúng mốc cần đánh giá cụ thể, không suy từ dấu lớn hoặc nhỏ.', [(315, ['Trật khớp khuỷu mới:', 'Trật khớp khuỷu cũ:'])]),
 ('Theo tổn thương phối hợp: đơn thuần hoặc kết hợp gãy xương.', [(315, ['Trật khớp khuỷu đơn thuần', 'Trật khớp khuỷu kết hợp'])]),
], book=21)
add('elbow', 'clinical-xray-diagnosis', 'Trình bày chẩn đoán trật khớp khuỷu.', [
 ('Lâm sàng có đau, mất vận động, khuỷu sưng biến dạng, tư thế gấp bắt buộc và lò xo, thay đổi tương quan các mốc xương.', [(315, ['Đau nhiều', 'Khuỷu sưng', 'Cẳng tay như', 'Khớp khuỷu ở', 'Tam giác Hunter'])]),
 ('Khám mạch quay, trụ, tưới máu và vận động cảm giác đầu chi để tìm tổn thương mạch thần kinh.', [(315, ['Cần khám mạch'])]),
 ('X-quang thẳng nghiêng xác định trật và gãy phối hợp; CT khi gãy phạm khớp, MRI khi nghi tổn thương dây chằng gây mất vững.', [(316, ['Cần chụp']), (317, ['Các trường hợp'])]),
 ('Phân biệt gãy đơn thuần vùng khuỷu, gãy trên lồi cầu, mỏm khuỷu, chỏm quay hoặc gãy trật Monteggia; không chỉ kết luận trật mà bỏ qua tổn thương phối hợp.', [(317, ['Phải chẩn đoán', 'Cần chẩn đoán'])]),
], book=2)
add('elbow', 'delayed-vascular', 'Vì sao sau trật khuỷu vẫn phải theo dõi mạch máu dù chưa có dấu đứt mạch rõ? Cần khám thần kinh nào?', [
 ('Động mạch cánh tay có thể bị kéo giãn, chèn ép hoặc tổn thương nội mạc gây tắc muộn; cần theo dõi mạch và tưới máu.', [(316, ['Về mạch máu:'])]),
 ('Khám thần kinh giữa, trụ và liên cốt trước qua vận động, cảm giác phù hợp để nhận diện tổn thương thần kinh.', [(316, ['Về thần kinh:'])]),
])
add('elbow', 'treatment-goals', 'Nêu nguyên tắc điều trị trật khuỷu và lý do vừa cần cố định sau nắn vừa cần phục hồi vận động hợp lý.', [
 ('Nắn về giải phẫu sớm, tìm và xử lý tổn thương phối hợp, không bỏ sót biến chứng.', [(317, ['Nắn chỉnh khớp', 'Không được bỏ sót'])]),
 ('Cố định đủ thời gian giúp bao khớp dây chằng liền; sau giai đoạn cố định cần tập phục hồi sớm để lấy lại biên độ, tránh cứng khuỷu.', [(313, ['Khớp khuỷu được giữ']), (317, ['Cố định sau', 'Tập phục hồi'])]),
])
add('elbow', 'post-reduction-assessment', 'Sau nắn khuỷu, ngoài cảm giác đã hết biến dạng, cần kiểm tra kết quả và độ vững bằng những cách nào theo giáo trình?', [
 ('Kiểm tra gấp duỗi, mức vững khi vận động, đồng thời khám lại mạch thần kinh và tổn thương phối hợp.', [(318, ['Tư thế bệnh nhân nằm sấp']), (317, ['Không được bỏ sót'])]),
 ('Chụp lại X-quang sau nắn để xác nhận vị trí và phát hiện mảnh gãy hoặc kẹt khớp; bất động và phục hồi tùy mức vững.', [(318, ['Phương pháp cố định'])]),
])
add('elbow', 'entrapped-fragment', 'Sau nắn trật khuỷu, khớp vẫn vận động không mềm mại. Cần nghĩ tới nguyên nhân gì và kiểm tra như thế nào?', [
 ('Cần nghĩ tới mảnh xương gãy bị kẹt trong khớp, đặc biệt mảnh vùng mỏm trên lồi cầu trong.', [(319, ['Trường hợp này', 'Thường gặp sau'])]),
 ('Kiểm tra X-quang để xác định; khi mảnh gây kẹt khớp có thể cần phẫu thuật lấy hoặc xử trí mảnh, không cố vận động thô bạo.', [(319, ['Thường gặp sau']), (321, ['Có thể mổ nội soi'])]),
])
add('elbow', 'terrible-triad', 'Bộ ba tổn thương nặng của khuỷu gồm những gì và gây lo ngại gì cho kết quả chức năng?', [
 ('Gồm trật khuỷu, gãy mỏm vẹt và gãy chỏm quay.', [(321, ['Theo Broberg'])]),
 ('Dễ mất vững hoặc trật tái phát, kết quả cơ năng kém; bất động kéo dài còn tăng nguy cơ cứng khuỷu.', [(321, ['Theo Broberg', 'Nói chung'])]),
])

add('forearm', 'forearm-function', 'Vì sao phục hồi gãy hai xương cẳng tay không chỉ cần liền xương? Nêu các yếu tố giải phẫu cần phục hồi để bảo đảm sấp ngửa.', [
 ('Hai xương và khớp quay trụ trên, dưới hoạt động phối hợp trong sấp ngửa; phải tìm tổn thương khớp đi kèm.', [(338, ['Quan hệ khớp'])]),
 ('Cần phục hồi chiều dài, trục, độ xoay và độ cong sinh lý xương quay để tránh hạn chế chức năng.', [(338, ['Quan hệ khớp']), (350, ['Đặc biệt nắn chỉnh'])]),
])
add('forearm', 'membrane', 'Màng gian cốt cẳng tay có những chức năng nào và vì sao cần tránh gây tổn thương thêm khi phẫu thuật?', [
 ('Màng gian cốt hỗ trợ sấp ngửa, truyền lực giữa hai xương, làm chỗ bám cơ và góp phần giữ vững dọc trục.', [(339, ['Xương quay và trụ'])]),
 ('Xâm phạm màng gian cốt bởi mảnh gãy, xương ghép hoặc mũi khoan là yếu tố nguy cơ dính quay trụ, ảnh hưởng sấp ngửa.', [(351, ['Sự thâm'])]),
])
add('forearm', 'monteggia-galeazzi', 'Phân biệt gãy trật Monteggia và Galeazzi; cần kiểm tra những khớp nào trên phim?', [
 ('Monteggia là gãy xương trụ đoạn trên kèm trật hoặc mất vững khớp quay trụ trên.', [(343, ['Với gãy xương trụ'])]),
 ('Galeazzi là gãy xương quay đoạn dưới kèm trật hoặc mất vững khớp quay trụ dưới; phim cần lấy cả khuỷu và cổ tay để tránh bỏ sót.', [(343, ['Với gãy xương trụ', 'Tư thế chụp:'])]),
])
add('forearm', 'clinical-radiographic', 'Trình bày các triệu chứng lâm sàng và X-quang gãy hai xương cẳng tay.', [
 ('Đau, mất cơ năng, sưng biến dạng và có thể ngắn chi; kiểm tra da để nhận diện gãy hở. Có thể có đau chói nhưng không chủ động tìm lạo xạo hay cử động bất thường.', [(343, ['Sau tai nạn', 'Quan sát', 'Khám lâm sàng có', 'Đo chiều dài'])]),
 ('Đánh giá mạch quay trụ, phản hồi mao mạch, chức năng quay trụ giữa; đau bất thường hoặc đau khi vận động thụ động ngón gợi ý chèn ép khoang.', [(343, ['Khám lâm sàng dấu hiệu'])]),
 ('X-quang thẳng nghiêng lấy khuỷu và cổ tay, đánh giá vị trí, hình thái, di lệch và trật khớp quay trụ trên hoặc dưới; có thể thêm chếch nếu chưa rõ.', [(343, ['Tư thế chụp:', 'Đánh giá:'])]),
], book=27)
add('forearm', 'adult-surgery', 'Trong gãy thân hai xương cẳng tay người lớn, khi nào giáo trình ưu tiên phẫu thuật? Vì sao thường dùng hai đường mổ riêng?', [
 ('Phẫu thuật khi bảo tồn không đạt, gãy kín một hoặc hai xương có di lệch ở người lớn và gãy hở; cần xét tình trạng mô mềm và người bệnh.', [(346, ['Điều trị bảo tồn không', 'Mọi loại gãy', 'Gãy xương hở'])]),
 ('Hai đường riêng cho quay và trụ nhằm giảm phá hủy mô mềm và nguy cơ can dính quay trụ làm hạn chế sấp ngửa.', [(346, ['Đường mổ:'])]),
])
add('forearm', 'distal-patterns', 'Phân biệt Colles, Smith và Barton về vị trí so với mặt khớp và hướng di lệch điển hình.', [
 ('Colles là gãy ngang ngoài khớp đầu dưới quay, thường do chống tay cổ tay duỗi, mảnh xa lệch lên trên, ra sau và sang phía quay.', [(358, ['Gãy ngang', 'Cơ chế hay', 'Di lệch điển hình'])]),
 ('Smith cũng ngoài khớp nhưng mảnh xa lệch ra trước, thường sau chống tay cổ tay gấp.', [(359, ['Gãy ngang', 'Cơ chế ngã'])]),
 ('Barton lan vào mặt khớp quay cổ tay và kèm trật hoặc bán trật khớp quay cổ tay.', [(357, ['Ngoài ra còn'])]),
])
add('forearm', 'distal-ao', 'Theo phần gãy đầu dưới xương quay của giáo trình, ba nhóm AO A, B, C phân biệt theo liên quan mặt khớp như thế nào?', [
 ('A: gãy không phạm khớp.', [(358, ['Nhóm A:'])]),
 ('B: gãy phạm khớp một phần.', [(358, ['Nhóm B:'])]),
 ('C: gãy phạm khớp phức tạp theo cách trình bày của giáo trình.', [(358, ['Nhóm C:'])]),
])
add('forearm', 'distal-median', 'Trong gãy đầu dưới quay, vì sao cần chú ý thần kinh giữa? Nêu cơ chế tổn thương được tài liệu mô tả.', [
 ('Cần thăm khám vận động cảm giác và loại trừ tổn thương thần kinh giữa, không chỉ đánh giá biến dạng cổ tay.', [(360, ['Ngoài ra cần thăm'])]),
 ('Mảnh gãy có thể gây tổn thương trực tiếp; máu tụ hoặc tăng áp lực ống cổ tay cũng gây chèn ép thần kinh giữa.', [(360, ['Ngoài ra cần thăm'])]),
])
add('forearm', 'distal-xray-ct', 'Khi đọc hình ảnh gãy đầu dưới quay, cần chụp tư thế nào, đánh giá những nhóm chỉ số nào và khi nào cân nhắc CT?', [
 ('Cần phim cổ tay thẳng nghiêng chất lượng tốt; trên phim thẳng xem góc nghiêng trụ, chiều cao mặt khớp và độ chênh quay trụ, trên phim nghiêng xem góc nghiêng lòng.', [(360, ['Tư thế:']), (361, ['Góc nghiêng trụ', 'Chiều cao', 'Độ chênh', 'Góc nghiêng lòng'])]),
 ('CT giúp đánh giá chi tiết khi gãy phức tạp lan vào diện khớp để lựa chọn điều trị, không thay thế việc đọc đầy đủ phim ban đầu.', [(361, ['Xem xét'])]),
])

add('hip', 'highenergy-associated', 'Vì sao nghi trật khớp háng sau tai nạn cần khám tổng thể thay vì chỉ khám vùng đau? Nêu các vùng tổn thương phối hợp cần lưu ý.', [
 ('Khớp háng vốn vững, trật thường do năng lượng cao và dễ đi kèm tổn thương khác.', [(423, ['Trật khớp háng là'])]),
 ('Tìm chấn thương sọ não, ngực bụng, khung chậu, cột sống và gối cùng bên; ưu tiên tổn thương đe dọa tính mạng.', [(427, ['Bệnh nhân trật']), (423, ['Ngoài ra có thể'])]),
])
add('hip', 'mechanisms', 'So sánh cơ chế trật háng ra sau và ra trước; cơ chế đầu gối đập vào bảng xe thường gây hướng trật nào?', [
 ('Gấp háng, khép đùi và lực dọc từ gối lên đùi đẩy chỏm ra sau; va đầu gối khi xe dừng đột ngột là ví dụ.', [(424, ['Ngã trong tư thế gấp háng và khép'])]),
 ('Gấp háng kèm dạng, xoay ngoài làm chỏm thúc bờ trước ổ cối và trật ra trước.', [(424, ['Ngã trong tư thế gấp háng,'])]),
])
add('hip', 'direction-types', 'Năm kiểu trật háng theo vị trí chỏm là gì? Phân biệt hai kiểu trước và hai kiểu sau.', [
 ('Kiểu chậu: sau trên; kiểu ngồi: sau dưới.', [(425, ['Kiểu chậu:', 'Kiểu ngồi:'])]),
 ('Kiểu mu: trước trên; kiểu bịt: trước dưới.', [(425, ['Kiểu mu:', 'Kiểu bịt:'])]),
 ('Trung tâm: chỏm xuyên vùng đáy ổ cối vào tiểu khung, khác với trật trước hoặc sau.', [(425, ['Trật khớp háng trung tâm:']), (424, ['Ổ cối do'])]),
])
add('hip', 'stewart-stability', 'Theo Steward–Milford trong giáo trình, bốn độ trật háng khác nhau như thế nào về gãy phối hợp và độ vững sau nắn?', [
 ('Độ 1: trật, sau nắn vững. Độ 2: kèm vỡ một phần chỏm hoặc ổ cối nhưng sau nắn vẫn vững.', [(425, ['Độ 1:', 'Độ 2:'])]),
 ('Độ 3: tổn thương như độ 2 nhưng khớp không vững, trật lại. Độ 4: kèm gãy cổ xương đùi; giáo trình xếp độ 3 và 4 vào nhóm cần phẫu thuật.', [(425, ['Độ 3:', 'Độ 4:', 'Trong 4 độ'])]),
])
add('hip', 'posture', 'Phân biệt tư thế chi trong trật háng ra trước và ra sau; hướng lên trên hoặc xuống dưới làm thay đổi độ gấp đùi ra sao?', [
 ('Ra sau thường khép và xoay trong; ra trước thường dạng và xoay ngoài.', [(427, ['Trật ra sau', 'Trật ra trước'])]),
 ('Trật lên trên gấp đùi ít hơn, trật xuống dưới gấp nhiều; có thể kèm kháng cự đàn hồi khi sửa tư thế.', [(427, ['Trật lên trên', 'Trật khớp háng xuống', 'Luôn luôn'])]),
])
add('hip', 'sciatic-screen', 'Trong trật háng, cần đặc biệt chú ý thần kinh nào và các cơ chế gây tổn thương thần kinh đó? Vì sao vẫn cần khám mạch?', [
 ('Thần kinh ngồi hoặc hông to dễ tổn thương do chỏm trật chèn ép hay mảnh vỡ xương chậu đè vào.', [(428, ['Cần khám các biến chứng'])]),
 ('Mạch đùi ít bị hơn nhưng vẫn có nguy cơ; khám tưới máu và thần kinh là phần bắt buộc để không bỏ sót tổn thương phối hợp.', [(428, ['Cần khám các biến chứng']), (438, ['Do đi phía trước'])]),
])
add('hip', 'imaging-loosebody', 'Trước trật háng nghi kèm vỡ ổ cối hoặc chỏm, cần chụp phạm vi X-quang nào và CT giúp giải quyết vấn đề gì?', [
 ('X-quang lấy toàn khung chậu và cả hai háng để so sánh vị trí chỏm, thể trật, liên tục cung Shenton và gãy phối hợp.', [(428, ['Chụp phim X quang', 'Đường Shenton', 'Cần đánh giá'])]),
 ('CT đánh giá đầy đủ vỡ ổ cối, chỏm và mảnh xương kẹt trong khớp, giúp lựa chọn xử trí.', [(429, ['Nếu có vỡ'])]),
])
add('hip', 'operative-indications', 'Theo giáo trình, nêu các nhóm tình huống cần cân nhắc phẫu thuật sau trật háng, không yêu cầu chọn đường mổ.', [
 ('Nắn bảo tồn thất bại, có mảnh kẹt khớp hoặc gãy chậu, chỏm gây mất vững sau nắn.', [(432, ['Nắn chỉnh bảo tồn', 'Có mảnh xương', 'Gãy xương chậu'])]),
 ('Kèm gãy cổ đùi, tổn thương mạch thần kinh hoặc trật cũ với tổ chức xơ lấp ổ cối.', [(432, ['Gãy cổ xương', 'Có biến chứng', 'Trật khớp háng cũ'])]),
])
add('hip', 'late-surveillance', 'Vì sao háng đã nắn về vẫn cần tái khám lâu dài? Nêu các biến chứng muộn chính và vai trò hình ảnh khi đau kéo dài.', [
 ('Hoại tử vô mạch chỏm có thể được phát hiện sau nhiều tháng hoặc nhiều năm do tổn thương mạch nuôi, nên nắn thành công không kết thúc theo dõi.', [(438, ['Hoại tử vô mạch', 'Hoại tử chỏm'])]),
 ('Có thể thoái hóa, vôi hoặc cốt hóa quanh khớp, trật tái phát; theo dõi lâm sàng và hình ảnh, cân nhắc MRI khi đau mà X-quang chưa giải thích được.', [(438, ['Thoái hóa khớp háng được', 'Do vôi hóa', 'Do tổn thương']), (437, ['Nên chụp'])]),
])

add('neck', 'anatomic-location', 'Gãy cổ xương đùi nằm ở đâu? Vì sao không thể nói mọi phần của đường gãy nền cổ đều nằm trong bao khớp?', [
 ('Gãy ở vùng giữa chỏm và khối mấu chuyển, đa phần là gãy nội khớp.', [(441, ['Gãy cổ xương đùi là'])]),
 ('Bao khớp phía sau chỉ phủ tới một phần cổ nên một phần nhỏ đường gãy nền cổ phía sau có thể nằm ngoài bao khớp.', [(443, ['Bao khớp là'])]),
])
add('neck', 'age-risk', 'So sánh bối cảnh gãy cổ đùi ở người trẻ và người cao tuổi; nêu những yếu tố làm tăng nguy cơ ở người cao tuổi.', [
 ('Người trẻ thường sau chấn thương năng lượng cao; người già có thể gãy sau ngã nhẹ.', [(441, ['Gãy cổ xương đùi có thể'])]),
 ('Loãng xương, giảm thị lực, giảm khả năng giữ thăng bằng hoặc bảo vệ khi ngã, bệnh mạn và dùng corticoid kéo dài là những yếu tố cần khai thác.', [(442, ['Tuổi:', 'Các bệnh lý']), (445, ['Theo các tác giả']), (446, ['kèm theo các bệnh'])]),
])
add('neck', 'vascular-necrosis', 'Giải thích vì sao gãy cổ xương đùi di lệch có nguy cơ hoại tử chỏm; động mạch dây chằng tròn có bảo đảm đủ nuôi chỏm không?', [
 ('Di lệch gây tổn thương hệ mạch quanh cổ, tăng áp lực trong bao khớp do máu tụ cũng có thể cản tưới máu.', [(445, ['Gãy cổ xương đùi là gãy nội khớp'])]),
 ('Động mạch dây chằng tròn nhỏ, có thể không có hoặc xơ vữa; thường không đủ nuôi chỏm khi gãy cổ di lệch.', [(444, ['Động mạch dây chằng tròn'])]),
])
add('neck', 'impaired-union', 'Theo mô tả sinh lý bệnh của giáo trình, những đặc điểm nội khớp nào khiến gãy cổ đùi khó liền?', [
 ('Cổ nằm trong bao khớp nên không tạo can ngoại vi như gãy thân xương; khả năng liền phụ thuộc nguồn từ trong xương còn lại.', [(443, ['Khi gãy, cổ'])]),
 ('Dịch khớp làm tiêu máu tụ, trong khi mất tưới máu do gãy và di lệch làm điều kiện liền xương xấu hơn.', [(443, ['Khi gãy, cổ']), (445, ['Gãy cổ xương đùi là gãy nội khớp'])]),
])
add('neck', 'garden', 'Trình bày bốn độ Garden trong gãy cổ đùi; phân biệt gãy hoàn toàn không di lệch với gãy hoàn toàn mất liên hệ giữa chỏm và cổ.', [
 ('Garden I: gãy không hoàn toàn, cài nhau; II: gãy hoàn toàn nhưng không di lệch.', [(447, ['Độ 1:', 'Độ 2:'])]),
 ('III: gãy hoàn toàn di lệch nhưng còn tiếp xúc hoặc dính nhau; IV: di lệch hoàn toàn, chỏm không còn dính cổ và có thể xoay tự do.', [(447, ['Độ 3:', 'Độ 4:'])]),
])
add('neck', 'pauwels', 'Phân loại Pauwels dựa trên góc nào? Nêu ba mức và giải thích vì sao đường gãy càng đứng càng khó liền.', [
 ('Góc giữa diện gãy và mặt phẳng ngang: độ I dưới 30°, II từ 30° đến 50°, III trên 50° theo giáo trình.', [(447, ['Dựa vào độ chệch', 'Độ 1: \\alpha', 'Độ 2: 30', 'Độ 3: 50'])]),
 ('Đường gãy ít dốc có thành phần ép ổ gãy thuận lợi; càng đứng, lực trượt ra ngoài diện gãy càng lớn và tiên lượng liền kém.', [(447, ['Độ 1: \\alpha', 'Độ 2: 30', 'Độ 3: 50'])]),
])
add('neck', 'occult-fracture', 'Người già ngã, đau háng nhưng ban đầu vẫn đi được: có loại trừ gãy cổ đùi không? Khi phim chưa rõ cần cân nhắc gì?', [
 ('Không loại trừ: gãy không di lệch có thể còn đi được rồi đau tăng hoặc mất vận động sau đó; cần khai thác diễn biến và thông tin từ người chăm sóc.', [(448, ['Cần khai thác kỹ thời gian'])]),
 ('Trong gãy không hoặc ít di lệch khó xác định, CT hoặc MRI giúp xác nhận; MRI có thể thấy ổ gãy kín đáo, máu tụ và tổn thương phần mềm.', [(449, ['Trong một số', 'Chụp cộng hưởng'])]),
])
add('neck', 'immobility-complications', 'Vì sao gãy cổ đùi ở người cao tuổi cần đánh giá toàn thân và tránh hậu quả nằm lâu? Nêu các biến chứng cần theo dõi.', [
 ('Người bệnh thường có nhiều bệnh nền, làm tăng nguy cơ biến chứng và tử vong; cần đánh giá tim phổi, bệnh thận và các bệnh phối hợp.', [(445, ['Gãy cổ xương đùi hay', 'Các yếu tố làm']), (448, ['Ở người già, thường'])]),
 ('Theo dõi viêm phổi, nhiễm trùng tiết niệu, loét tỳ đè, huyết khối tĩnh mạch sâu và tắc mạch phổi.', [(445, ['Gãy cổ xương đùi hay'])]),
])
add('neck', 'nonunion-signs', 'Sau điều trị gãy cổ đùi, biểu hiện nào gợi ý khớp giả và phải xem những yếu tố gì trước khi chọn cách xử trí?', [
 ('Đau háng hoặc đùi khi đi, khó tự đi, có thể ngắn chi; X-quang thấy khe sáng ổ gãy cũ, mất xương, tiêu chỏm hoặc lệch trục.', [(457, ['Bệnh nhân có dấu hiệu'])]),
 ('Lựa chọn phụ thuộc khuyết xương, mức tiêu chỏm, tuổi, nhu cầu vận động và bệnh toàn thân; các phương án gồm cố định lại, ghép xương, sửa trục hoặc thay khớp, không có một cách áp dụng cho mọi ca.', [(457, ['Điều trị: Tùy'])]),
])

add('spine', 'transition-risk', 'Vì sao đoạn ngực–thắt lưng chuyển tiếp dễ bị chấn thương hơn đoạn ngực giữa? Tài liệu xác định vùng chuyển tiếp nào?', [
 ('Đoạn ngực tương đối ít di động do các diện khớp và khung sườn ức giữ vững.', [(227, ['Các đoạn cột sống'])]),
 ('Vùng T11–L2 chuyển tiếp giữa đoạn cố định và đoạn di động với biên độ gấp, duỗi, xoay lớn nên dễ tổn thương.', [(227, ['Các đoạn cột sống']), (228, ['giữa đoạn'])]),
])
add('spine', 'force-morphology', 'Liên hệ lực nén dọc, lực gấp–căng giãn và lực xé với hình thái tổn thương cột sống ngực–thắt lưng.', [
 ('Nén dọc có thể gây lún hoặc vỡ thân đốt có mảnh rời.', [(228, ['A:'])]),
 ('Gấp kết hợp căng giãn gây gãy Chance và các biến thể, gắn với cơ chế đai an toàn.', [(228, ['B:', 'F:'])]),
 ('Lực xé gây mất vững rõ, có thể gãy kèm trật đốt sống.', [(228, ['D:'])]),
])
add('spine', 'ankylosis-osteoporosis', 'Trong chấn thương cột sống, vì sao cần hỏi viêm cột sống dính khớp và loãng xương dù lực chấn thương có vẻ nhẹ?', [
 ('Ở người viêm cột sống dính khớp, lực nhẹ như ngã từ tư thế đứng vẫn có thể gây chấn thương cột sống.', [(229, ['Viêm cột sống'])]),
 ('Loãng xương làm tăng nguy cơ gãy; cần tìm gãy phối hợp như chậu, cổ đùi hoặc đầu dưới quay và các bệnh nền ảnh hưởng xử trí.', [(229, ['Loãng xương:', 'Ngoài ra'])]),
])
add('spine', 'initial-priorities', 'Nêu thứ tự ưu tiên đánh giá ban đầu và nguyên tắc giữ tư thế khi thăm khám người nghi chấn thương cột sống.', [
 ('Ưu tiên đường thở, hô hấp, tuần hoàn rồi đánh giá thần kinh; đánh giá toàn thân trước khám khu trú.', [(229, ['Khi bệnh nhân mới'])]),
 ('Giữ trục cột sống, cố định chắc; chỉ nghiêng khám khi điều kiện cho phép và có bảo vệ, không xoay vặn tùy tiện.', [(229, ['Tôn trọng tư thế']), (239, ['Cố định cột sống'])]),
])
add('spine', 'motor-mapping', 'Trong khám thần kinh chi dưới sau chấn thương cột sống, nêu các rễ chủ yếu được đánh giá bằng gấp háng, duỗi gối, gấp mu cổ chân, duỗi ngón cái và gấp gan chân.', [
 ('Gấp háng: L2; duỗi gối: L3; gấp mu cổ chân: L4.', [(230, ['Gập háng', 'L2', 'Duỗi gối', 'L3', 'Gập mu chân', 'L4'])]),
 ('Duỗi ngón cái: L5; gấp gan chân: S1. Ghi từng động tác để theo dõi thay đổi thần kinh, không chỉ ghi chung là có hoặc không liệt.', [(230, ['Duỗi ngón cái', 'L5', 'Gập gan chân', 'S1', 'Mỗi động tác'])]),
])
add('spine', 'motor-grades', 'Phân biệt các mức cơ lực 0–1, 2–3 và 4–5 trong khám sau chấn thương cột sống.', [
 ('0: không co cơ; 1: có co cơ quan sát hoặc sờ được nhưng chưa tạo vận động hữu hiệu.', [(230, ['Bậc 0:', 'Bậc 1:'])]),
 ('2: vận động khi loại trọng lực; 3: vận động hết tầm thắng trọng lực.', [(230, ['Bậc 2:', 'Bậc 3:'])]),
 ('4: thắng thêm sức cản nhưng chưa bình thường; 5: cơ lực bình thường.', [(230, ['Bậc 4:', 'Bậc 5'])]),
])
add('spine', 'ct-mri-complement', 'Trong chấn thương ngực–thắt lưng, so sánh vai trò CT và MRI, đặc biệt với xương, tủy và phức hợp dây chằng phía sau.', [
 ('CT nhạy hơn X-quang thường quy trong đánh giá tổn thương xương, nhưng hạn chế với phần mềm.', [(234, ['CLVT có'])]),
 ('MRI đánh giá tủy, phù, xuất huyết, máu tụ và dây chằng phía sau; bổ sung cho CT chứ không thay hoàn toàn CT trong đánh giá thành phần xương.', [(234, ['CHT đánh giá'])]),
])
add('spine', 'tlic-dimensions', 'Thang TLIC đánh giá ba thành phần nào? Vì sao phân loại hình thái xương đơn thuần chưa đủ để định hướng điều trị?', [
 ('Ba thành phần là hình thái tổn thương đốt sống, tình trạng phức hợp dây chằng phía sau và mức tổn thương thần kinh.', [(235, ['TLIC ('])]),
 ('Dây chằng ảnh hưởng độ vững và thần kinh phản ánh hậu quả chức năng; TLIC tổng hợp các yếu tố này để định hướng điều trị thay vì chỉ gọi tên kiểu gãy.', [(239, ['Phân loại TLIC'])]),
])
