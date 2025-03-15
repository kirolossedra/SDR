%% Generate and Decode a Single MPDU Example
% Create a MAC frame configuration object for a Data frame using HE-SU.
cfgMPDU = wlanMACFrameConfig('FrameType','Data','FrameFormat','HE-SU');

% Create a random MSDU (data payload) of 32 octets.
msdu = randi([0 255],32,1);

% Display the original MSDU.
disp('Original MSDDU (numeric values):');
disp(msdu.');

% Generate the MPDU from the MSDU with output in bits.
[mpdu, mpduLength] = wlanMACFrame(msdu, cfgMPDU, 'OutputFormat','bits');

% Display the generated MPDU (MAC frame) in bits.
disp('Generated MPDU (bits):');
disp(mpdu.');

% Decode the MPDU to recover the payload.
[rxCfgMPDU, payload, status] = wlanMPDUDecode(mpdu, wlanHESUConfig);

% Check and display if the frame formats match.
disp(['FrameFormat match: ' num2str(isequal(cfgMPDU.FrameFormat, rxCfgMPDU.FrameFormat))]);
disp(['MPDU decoding status: ' char(status)]);

% Display the recovered payload.
disp('Recovered MSDU (numeric values):');
disp(payload.');

%% Generate and Parse an A-MPDU Example
% Create a MAC frame configuration object for a QoS Data frame with aggregation.
cfgAMPDU = wlanMACFrameConfig('FrameType','QoS Data','FrameFormat','HE-SU',... 
    'MPDUAggregation', true, 'MSDUAggregation', false);

% Create a cell array of 4 MSDUs (each a 32-octet random vector).
msduList = repmat({randi([0 255],32,1)}, 1, 4);

% Display each original MSDU in the A-MPDU list.
disp('Original MSDU List for A-MPDU:');
for i = 1:numel(msduList)
    fprintf('MSDU %d: ', i);
    disp(msduList{i}.');
end

% Specify the HE-SU PHY configuration (e.g., using MCS 5).
cfgPHY = wlanHESUConfig('MCS', 5);

% Generate the A-MPDU (aggregate frame) with output in bits.
[ampdu, ampduLength] = wlanMACFrame(msduList, cfgAMPDU, cfgPHY, 'OutputFormat', 'bits');

% Display the generated A-MPDU in bits.
disp('Generated A-MPDU (bits):');
disp(ampdu.');

% Deaggregate the A-MPDU into individual MPDUs.
[mpduList, delimiterCRCFailure, status] = wlanAMPDUDeaggregate(ampdu, cfgPHY);

% Display the deaggregation status.
disp(['Number of Delimiter CRC Failures: ' num2str(nnz(delimiterCRCFailure))]);
disp(['A-MPDU deaggregation status: ' char(status)]);

% If deaggregation is successful, decode each MPDU.
if strcmp(status, 'Success')
    for i = 1:numel(mpduList)
        if ~delimiterCRCFailure(i)
            [cfg, msdu_decoded, decodeStatus] = wlanMPDUDecode(mpduList{i}, cfgPHY, 'DataFormat','octets');
            disp(['MPDU ' num2str(i) ' decoding status: ' char(decodeStatus)]);
            disp(['Recovered MSDU from MPDU ' num2str(i) ':']);
            disp(msdu_decoded.');
        else
            disp(['MPDU ' num2str(i) ' has a CRC failure and was not decoded.']);
        end
    end
else
    disp('A-MPDU deaggregation was not successful.');
end
